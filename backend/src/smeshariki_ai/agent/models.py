from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
NonEmptyFragment = Annotated[str, StringConstraints(min_length=1)]


class AgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LLMResultType(StrEnum):
    FINAL = "final"
    TOOL_CALL = "tool_call"
    INVALID = "invalid"


class ToolCall(AgentModel):
    id: NonEmptyString
    name: NonEmptyString
    arguments: dict[str, Any] = Field(default_factory=dict)


class UserRequest(AgentModel):
    content: NonEmptyString


class AgentConfig(AgentModel):
    system_prompt: str
    max_iterations: int = Field(default=4, gt=0)


class ToolDefinition(AgentModel):
    name: NonEmptyString
    description: NonEmptyString
    parameters: dict[str, Any]


class ToolError(AgentModel):
    code: NonEmptyString
    message: NonEmptyString


class ToolResult(AgentModel):
    call_id: NonEmptyString
    name: NonEmptyString
    output: Any = None
    error: ToolError | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None


class Message(AgentModel):
    role: MessageRole
    content: str = ""
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None


class LLMResponse(AgentModel):
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


class LLMTextDelta(AgentModel):
    content: NonEmptyFragment


class AgentTextDelta(AgentModel):
    content: NonEmptyFragment


class AgentResponse(AgentModel):
    content: str
