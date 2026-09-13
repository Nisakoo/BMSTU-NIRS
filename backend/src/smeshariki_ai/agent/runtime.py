import logging
from collections.abc import Sequence

from smeshariki_ai.agent.errors import (
    AgentIterationLimitError,
    InvalidLLMResponseError,
)
from smeshariki_ai.agent.llm import LLMProvider
from smeshariki_ai.agent.models import (
    AgentConfig,
    AgentResponse,
    LLMResponse,
    LLMResultType,
    Message,
    MessageRole,
    UserRequest,
)
from smeshariki_ai.agent.tools import ToolRegistry

logger = logging.getLogger(__name__)


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
    ) -> AgentResponse:
        logger.info(
            "agent.run.started",
            extra={
                "history_size": len(history),
                "max_iterations": self._config.max_iterations,
            },
        )
        context = [
            Message(role=MessageRole.SYSTEM, content=self._config.system_prompt),
            *history,
            Message(role=MessageRole.USER, content=request.content),
        ]

        try:
            for iteration in range(1, self._config.max_iterations + 1):
                logger.info(
                    "agent.iteration.started",
                    extra={"iteration": iteration},
                )
                llm_response = await self._llm_provider.generate(
                    tuple(context),
                    self._tool_registry.definitions,
                )
                result_type = self._result_type(llm_response)
                logger.info(
                    "agent.llm.completed",
                    extra={
                        "iteration": iteration,
                        "result_type": result_type.value,
                    },
                )

                if result_type is LLMResultType.INVALID:
                    raise InvalidLLMResponseError(
                        "The LLM provider returned an invalid response."
                    )

                if result_type is LLMResultType.FINAL:
                    assert llm_response.content is not None
                    logger.info(
                        "agent.run.completed",
                        extra={"iterations": iteration},
                    )
                    return AgentResponse(content=llm_response.content)

                for tool_call in llm_response.tool_calls:
                    context.append(
                        Message(
                            role=MessageRole.ASSISTANT,
                            tool_call=tool_call,
                        )
                    )
                    tool_result = await self._tool_registry.execute(tool_call)
                    logger.info(
                        "agent.tool.completed",
                        extra={
                            "iteration": iteration,
                            "tool_name": tool_call.name,
                            "tool_status": (
                                "error" if tool_result.is_error else "success"
                            ),
                        },
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
        except Exception as error:
            logger.error(
                "agent.run.failed",
                extra={"error_type": type(error).__name__},
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
