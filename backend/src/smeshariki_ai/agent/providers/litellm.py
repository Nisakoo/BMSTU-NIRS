import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import litellm as litellm_sdk

from smeshariki_ai.agent.models import (
    LLMResponse,
    LLMTextDelta,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
)
from smeshariki_ai.agent.providers.base import (
    LLMProvider,
    LLMProviderError,
    LLMStreamEvent,
)
from smeshariki_ai.agent.providers.config import LiteLLMProviderConfig
from smeshariki_ai.observability import bind_context, log_event, utc_now

logger = logging.getLogger(__name__)


@dataclass
class _ToolCallParts:
    id: str = ""
    name: str = ""
    arguments: str = ""


class LiteLLMProvider(LLMProvider):
    def __init__(self, config: LiteLLMProviderConfig) -> None:
        self._config = config

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> AsyncIterator[LLMStreamEvent]:
        started_at = utc_now()
        started = time.monotonic()
        call_id = str(uuid4())
        first_token_ms: float | None = None
        usage: dict[str, int] | None = None
        stage = "message"
        common = {
            "model": self._config.model,
            "message_count": len(messages),
            "tool_count": len(tools),
        }
        with bind_context(call_id=call_id):
            log_event(logger, logging.INFO, "llm.request.started", **common)
            try:
                request = self._build_request(messages, tools)
                stage = "request"
                response_stream = await litellm_sdk.acompletion(**request)
                stage = "response"

                content_parts: list[str] = []
                tool_call_parts: dict[int, _ToolCallParts] = {}
                saw_choice = False

                async for chunk in response_stream:
                    chunk_usage = getattr(chunk, "usage", None)
                    if chunk_usage is not None:
                        usage = self._parse_usage(chunk_usage)
                    choices = chunk.choices
                    if not choices:
                        continue
                    if len(choices) != 1:
                        raise TypeError("A stream chunk must contain one choice.")

                    saw_choice = True
                    delta = choices[0].delta
                    content = delta.content
                    external_tool_calls = delta.tool_calls or ()

                    if content is not None and not isinstance(content, str):
                        raise TypeError("Stream content must be text or null.")
                    if content and external_tool_calls:
                        raise TypeError(
                            "A stream chunk cannot mix text and tool calls."
                        )
                    if content and tool_call_parts:
                        raise TypeError("A response cannot mix text and tool calls.")
                    if external_tool_calls and content_parts:
                        raise TypeError("A response cannot mix text and tool calls.")

                    if content:
                        if first_token_ms is None:
                            first_token_ms = round(
                                (time.monotonic() - started) * 1000, 3
                            )
                            log_event(
                                logger,
                                logging.DEBUG,
                                "llm.response.first_token",
                                time_to_first_token_ms=first_token_ms,
                            )
                        content_parts.append(content)
                        yield LLMTextDelta(content=content)

                    for external_call in external_tool_calls:
                        index = external_call.index
                        if not isinstance(index, int) or index != 0:
                            raise TypeError("Only one tool call is supported.")
                        parts = tool_call_parts.setdefault(index, _ToolCallParts())
                        if external_call.id is not None:
                            if not isinstance(external_call.id, str):
                                raise TypeError("Tool call id must be text.")
                            parts.id += external_call.id

                        function = external_call.function
                        if function.name is not None:
                            if not isinstance(function.name, str):
                                raise TypeError("Tool call name must be text.")
                            parts.name += function.name
                        if not isinstance(function.arguments, str):
                            raise TypeError("Tool call arguments must be text.")
                        parts.arguments += function.arguments

                if not saw_choice:
                    raise TypeError("The LLM stream did not contain a choice.")

                if tool_call_parts:
                    parts = tool_call_parts[0]
                    arguments = json.loads(parts.arguments)
                    if not isinstance(arguments, dict):
                        raise TypeError("Tool call arguments must be a JSON object.")
                    result = LLMResponse(
                        tool_calls=(
                            ToolCall(
                                id=parts.id,
                                name=parts.name,
                                arguments=arguments,
                            ),
                        )
                    )
                else:
                    result = LLMResponse(content="".join(content_parts))
            except asyncio.CancelledError:
                log_event(
                    logger,
                    logging.INFO,
                    "llm.request.cancelled",
                    **common,
                    started_at=started_at,
                    duration_ms=round((time.monotonic() - started) * 1000, 3),
                    outcome="cancelled",
                    usage_available=usage is not None,
                )
                raise
            except Exception as error:
                self._log_failure(error, common, started_at, started, usage)
                message = {
                    "message": "The LLM provider received an invalid message.",
                    "request": "The LLM provider request failed.",
                    "response": "The LLM provider returned an invalid response.",
                }[stage]
                raise LLMProviderError(message) from error

            log_event(
                logger,
                logging.INFO,
                "llm.request.completed",
                **common,
                started_at=started_at,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                outcome="completed",
                time_to_first_token_ms=first_token_ms,
                usage_available=usage is not None,
                input_tokens=usage["input_tokens"] if usage else None,
                output_tokens=usage["output_tokens"] if usage else None,
                total_tokens=usage["total_tokens"] if usage else None,
            )
            yield result

    @staticmethod
    def _parse_usage(value: Any) -> dict[str, int] | None:
        names = {
            "input_tokens": "prompt_tokens",
            "output_tokens": "completion_tokens",
            "total_tokens": "total_tokens",
        }
        result = {name: getattr(value, source, None) for name, source in names.items()}
        if any(type(number) is not int or number < 0 for number in result.values()):
            return None
        return result

    def _build_request(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self._config.model,
            "messages": [self._map_message(message) for message in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
            "timeout": self._config.timeout_seconds,
            "num_retries": self._config.num_retries,
        }
        if self._config.api_key is not None:
            request["api_key"] = self._config.api_key.get_secret_value()
        if self._config.base_url is not None:
            request["base_url"] = str(self._config.base_url)
        if tools:
            request["tools"] = [self._map_tool(tool) for tool in tools]
        return request

    @staticmethod
    def _map_message(message: Message) -> dict[str, Any]:
        if message.role is MessageRole.ASSISTANT and message.tool_call is not None:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": message.tool_call.id,
                        "type": "function",
                        "function": {
                            "name": message.tool_call.name,
                            "arguments": json.dumps(
                                message.tool_call.arguments,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        },
                    }
                ],
            }

        if message.role is MessageRole.TOOL:
            if (
                message.tool_call_id is None
                or message.tool_name is None
                or message.tool_result is None
            ):
                raise LLMProviderError("The LLM provider message is invalid.")
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "name": message.tool_name,
                "content": message.tool_result.model_dump_json(),
            }

        return {"role": message.role.value, "content": message.content}

    @staticmethod
    def _map_tool(tool: ToolDefinition) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    def _log_failure(
        self,
        error: Exception,
        common: dict[str, Any],
        started_at: str,
        started: float,
        usage: dict[str, int] | None,
    ) -> None:
        log_event(
            logger,
            logging.ERROR,
            "llm.request.failed",
            **common,
            error_type=type(error).__name__,
            started_at=started_at,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
            outcome="failed",
            usage_available=usage is not None,
        )
