import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from types import MappingProxyType
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError
from pydantic_core import to_jsonable_python

from smeshariki_ai.agent.errors import DuplicateToolError
from smeshariki_ai.agent.models import ToolCall, ToolDefinition, ToolError, ToolResult

logger = logging.getLogger(__name__)


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    arguments_model: ClassVar[type[BaseModel]]

    @abstractmethod
    async def execute(self, arguments: BaseModel) -> Any:
        """Execute the tool with already validated arguments."""


class ToolRegistry:
    def __init__(self, tools: Sequence[Tool]) -> None:
        tools_by_name: dict[str, Tool] = {}
        definitions: list[ToolDefinition] = []

        for tool in tools:
            if tool.name in tools_by_name:
                raise DuplicateToolError(f"Duplicate tool name: {tool.name}")

            tools_by_name[tool.name] = tool
            definitions.append(
                ToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.arguments_model.model_json_schema(),
                )
            )

        self._tools = MappingProxyType(tools_by_name)
        self._definitions = tuple(definitions)

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        return self._definitions

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        tool = self.get(tool_call.name)
        if tool is None:
            return ToolResult(
                call_id=tool_call.id,
                name=tool_call.name,
                error=ToolError(
                    code="tool_not_found",
                    message="The requested tool is not available.",
                ),
            )

        try:
            arguments = tool.arguments_model.model_validate(tool_call.arguments)
        except ValidationError:
            return ToolResult(
                call_id=tool_call.id,
                name=tool_call.name,
                error=ToolError(
                    code="invalid_arguments",
                    message="The tool arguments are invalid.",
                ),
            )

        try:
            output = await tool.execute(arguments)
            json_output = to_jsonable_python(output)
        except Exception as error:
            logger.error(
                "agent.tool.execution_failed tool_name=%s error_type=%s",
                tool.name,
                type(error).__name__,
                extra={
                    "tool_name": tool.name,
                    "error_type": type(error).__name__,
                },
            )
            return ToolResult(
                call_id=tool_call.id,
                name=tool_call.name,
                error=ToolError(
                    code="tool_execution_failed",
                    message="The tool could not be executed.",
                ),
            )

        return ToolResult(
            call_id=tool_call.id,
            name=tool_call.name,
            output=json_output,
        )
