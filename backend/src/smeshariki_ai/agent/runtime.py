import asyncio
import logging
import time
from collections.abc import AsyncIterator, Sequence

from smeshariki_ai.agent.errors import (
    AgentIterationLimitError,
    InvalidLLMResponseError,
)
from smeshariki_ai.agent.models import (
    AgentConfig,
    AgentResponse,
    AgentTextDelta,
    LLMResponse,
    LLMResultType,
    LLMTextDelta,
    Message,
    MessageRole,
    UserRequest,
)
from smeshariki_ai.agent.providers import LLMProvider
from smeshariki_ai.agent.tools import ToolRegistry
from smeshariki_ai.observability import bind_context, log_event, utc_now

logger = logging.getLogger(__name__)

AgentStreamEvent = AgentTextDelta | AgentResponse


class Agent:
    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry,
        config: AgentConfig,
    ) -> None:
        self._llm_provider = llm_provider
        self._tool_registry = tool_registry
        self._config = config

    async def run(
        self,
        history: Sequence[Message],
        request: UserRequest,
    ) -> AsyncIterator[AgentStreamEvent]:
        started_at = utc_now()
        started = time.monotonic()
        log_event(
            logger,
            logging.INFO,
            "agent.run.started",
            history_size=len(history),
            max_iterations=self._config.max_iterations,
        )
        context = [
            Message(role=MessageRole.SYSTEM, content=self._config.system_prompt),
            *history,
            Message(role=MessageRole.USER, content=request.content),
        ]

        try:
            for iteration in range(1, self._config.max_iterations + 1):
                log_event(
                    logger, logging.INFO, "agent.iteration.started", iteration=iteration
                )
                llm_response: LLMResponse | None = None
                content_parts: list[str] = []
                async for event in self._llm_provider.stream(
                    tuple(context), self._tool_registry.definitions
                ):
                    if isinstance(event, LLMTextDelta):
                        if llm_response is not None:
                            raise InvalidLLMResponseError(
                                "The LLM provider returned an invalid response."
                            )
                        content_parts.append(event.content)
                        yield AgentTextDelta(content=event.content)
                    elif isinstance(event, LLMResponse):
                        if llm_response is not None:
                            raise InvalidLLMResponseError(
                                "The LLM provider returned an invalid response."
                            )
                        llm_response = event
                    else:
                        raise InvalidLLMResponseError(
                            "The LLM provider returned an invalid response."
                        )

                if llm_response is None:
                    raise InvalidLLMResponseError(
                        "The LLM provider returned an invalid response."
                    )
                result_type = self._result_type(llm_response)
                log_event(
                    logger,
                    logging.INFO,
                    "agent.llm.completed",
                    iteration=iteration,
                    result_type=result_type.value,
                )

                if result_type is LLMResultType.INVALID:
                    raise InvalidLLMResponseError(
                        "The LLM provider returned an invalid response."
                    )

                if result_type is LLMResultType.FINAL:
                    assert llm_response.content is not None
                    if "".join(content_parts) != llm_response.content:
                        raise InvalidLLMResponseError(
                            "The LLM provider returned an invalid response."
                        )
                    log_event(
                        logger,
                        logging.INFO,
                        "agent.run.completed",
                        iterations=iteration,
                        started_at=started_at,
                        duration_ms=round((time.monotonic() - started) * 1000, 3),
                        outcome="completed",
                    )
                    yield AgentResponse(content=llm_response.content)
                    return

                if content_parts:
                    raise InvalidLLMResponseError(
                        "The LLM provider returned an invalid response."
                    )

                for tool_call in llm_response.tool_calls:
                    tool_name = (
                        tool_call.name
                        if self._tool_registry.get(tool_call.name) is not None
                        else "<unknown>"
                    )
                    context.append(
                        Message(
                            role=MessageRole.ASSISTANT,
                            tool_call=tool_call,
                        )
                    )
                    tool_started_at = utc_now()
                    tool_started = time.monotonic()
                    with bind_context(tool_call_id=tool_call.id):
                        log_event(
                            logger,
                            logging.INFO,
                            "agent.tool.started",
                            iteration=iteration,
                            tool_name=tool_name,
                        )
                        try:
                            tool_result = await self._tool_registry.execute(tool_call)
                        except asyncio.CancelledError:
                            log_event(
                                logger,
                                logging.INFO,
                                "agent.tool.cancelled",
                                iteration=iteration,
                                tool_name=tool_name,
                                started_at=tool_started_at,
                                duration_ms=round(
                                    (time.monotonic() - tool_started) * 1000, 3
                                ),
                                outcome="cancelled",
                            )
                            raise
                        log_event(
                            logger,
                            logging.INFO if not tool_result.is_error else logging.ERROR,
                            "agent.tool.completed",
                            iteration=iteration,
                            tool_name=tool_name,
                            tool_status="error" if tool_result.is_error else "success",
                            started_at=tool_started_at,
                            duration_ms=round(
                                (time.monotonic() - tool_started) * 1000, 3
                            ),
                            outcome="failed" if tool_result.is_error else "completed",
                        )
                    context.append(
                        Message(
                            role=MessageRole.TOOL,
                            tool_call_id=tool_call.id,
                            tool_name=tool_call.name,
                            tool_result=tool_result,
                        )
                    )

            raise AgentIterationLimitError(
                "The agent reached its iteration limit without a final response."
            )
        except asyncio.CancelledError:
            log_event(
                logger,
                logging.INFO,
                "agent.run.cancelled",
                started_at=started_at,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                outcome="cancelled",
            )
            raise
        except Exception as error:
            log_event(
                logger,
                logging.ERROR,
                "agent.run.failed",
                error_type=type(error).__name__,
                started_at=started_at,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                outcome="failed",
            )
            raise

    @staticmethod
    def _result_type(response: LLMResponse) -> LLMResultType:
        tool_call_count = len(response.tool_calls)
        has_content = response.content is not None

        if has_content and tool_call_count == 0:
            return LLMResultType.FINAL
        if not has_content and tool_call_count == 1:
            return LLMResultType.TOOL_CALL
        return LLMResultType.INVALID
