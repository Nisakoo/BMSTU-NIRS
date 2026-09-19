import json
import logging
from collections.abc import Sequence
from typing import Any

import litellm as litellm_sdk

from smeshariki_ai.agent.models import (
    LLMResponse,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
)
from smeshariki_ai.agent.providers.base import LLMProvider, LLMProviderError
from smeshariki_ai.agent.providers.config import LiteLLMProviderConfig

logger = logging.getLogger(__name__)


class LiteLLMProvider(LLMProvider):
    def __init__(self, config: LiteLLMProviderConfig) -> None:
        self._config = config

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> LLMResponse:
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
            response = await litellm_sdk.acompletion(**request)
        except Exception as error:
            self._log_failure(error)
            raise LLMProviderError("The LLM provider request failed.") from error

        try:
            result = self._map_response(response)
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
        return result

    def _build_request(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self._config.model,
            "messages": [self._map_message(message) for message in messages],
            "stream": False,
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

    @staticmethod
    def _map_response(response: Any) -> LLMResponse:
        message = response.choices[0].message
        if message.content is not None and not isinstance(message.content, str):
            raise TypeError("LLM response content must be text or null.")

        tool_calls = []
        for external_call in message.tool_calls or ():
            raw_arguments = external_call.function.arguments
            if not isinstance(raw_arguments, str):
                raise TypeError("Tool call arguments must be a JSON string.")
            arguments = json.loads(raw_arguments)
            if not isinstance(arguments, dict):
                raise TypeError("Tool call arguments must be a JSON object.")
            tool_calls.append(
                ToolCall(
                    id=external_call.id,
                    name=external_call.function.name,
                    arguments=arguments,
                )
            )
        return LLMResponse(content=message.content, tool_calls=tool_calls)

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
