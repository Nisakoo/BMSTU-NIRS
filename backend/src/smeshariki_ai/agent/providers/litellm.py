import json
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

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
        logger.info(
            "llm.request.started model=%s message_count=%d tool_count=%d",
            self._config.model,
            len(messages),
            len(tools),
            extra={
                "model": self._config.model,
                "message_count": len(messages),
                "tool_count": len(tools),
            },
        )
        try:
            request = self._build_request(messages, tools)
        except Exception as error:
            self._log_failure(error)
            raise LLMProviderError(
                "The LLM provider received an invalid message."
            ) from error

        try:
            response_stream = await litellm_sdk.acompletion(**request)
        except Exception as error:
            self._log_failure(error)
            raise LLMProviderError("The LLM provider request failed.") from error

        try:
            content_parts: list[str] = []
            tool_call_parts: dict[int, _ToolCallParts] = {}
            saw_choice = False

            async for chunk in response_stream:
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
                    raise TypeError("A stream chunk cannot mix text and tool calls.")
                if content and tool_call_parts:
                    raise TypeError("A response cannot mix text and tool calls.")
                if external_tool_calls and content_parts:
                    raise TypeError("A response cannot mix text and tool calls.")

                if content:
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
        except Exception as error:
            self._log_failure(error)
            raise LLMProviderError(
                "The LLM provider returned an invalid response."
            ) from error

        logger.info(
            "llm.request.completed model=%s message_count=%d tool_count=%d",
            self._config.model,
            len(messages),
            len(tools),
            extra={
                "model": self._config.model,
                "message_count": len(messages),
                "tool_count": len(tools),
            },
        )
        yield result

    def _build_request(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self._config.model,
            "messages": [self._map_message(message) for message in messages],
            "stream": True,
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

    def _log_failure(self, error: Exception) -> None:
        logger.error(
            "llm.request.failed model=%s error_type=%s",
            self._config.model,
            type(error).__name__,
            extra={
                "model": self._config.model,
                "error_type": type(error).__name__,
            },
        )
