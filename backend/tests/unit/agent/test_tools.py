from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from smeshariki_ai.agent.errors import DuplicateToolError
from smeshariki_ai.agent.models import ToolCall
from smeshariki_ai.agent.tools import Tool, ToolRegistry


class EchoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class EchoTool(Tool):
    name: ClassVar[str] = "echo"
    description: ClassVar[str] = "Return the supplied text."
    arguments_model: ClassVar[type[BaseModel]] = EchoArguments

    def __init__(self) -> None:
        self.calls: list[EchoArguments] = []

    async def execute(self, arguments: BaseModel) -> object:
        assert isinstance(arguments, EchoArguments)
        self.calls.append(arguments)
        return {"text": arguments.text}


class FailingTool(Tool):
    name: ClassVar[str] = "failing"
    description: ClassVar[str] = "Always fails."
    arguments_model: ClassVar[type[BaseModel]] = EchoArguments

    async def execute(self, arguments: BaseModel) -> object:
        raise RuntimeError("sensitive implementation detail")


def test_empty_registry_has_no_definitions() -> None:
    registry = ToolRegistry([])

    assert registry.definitions == ()


def test_registry_builds_definitions_in_registration_order() -> None:
    registry = ToolRegistry([EchoTool(), FailingTool()])

    assert [definition.name for definition in registry.definitions] == [
        "echo",
        "failing",
    ]
    assert registry.definitions[0].parameters["properties"]["text"]["type"] == "string"
    assert registry.get("echo") is not None
    assert registry.get("missing") is None


def test_registry_rejects_duplicate_names() -> None:
    with pytest.raises(DuplicateToolError, match="echo"):
        ToolRegistry([EchoTool(), EchoTool()])


@pytest.mark.asyncio
async def test_registry_validates_and_executes_registered_tool() -> None:
    tool = EchoTool()
    registry = ToolRegistry([tool])

    result = await registry.execute(
        ToolCall(id="call-1", name="echo", arguments={"text": "hello"})
    )

    assert result.call_id == "call-1"
    assert result.name == "echo"
    assert result.output == {"text": "hello"}
    assert result.error is None
    assert tool.calls == [EchoArguments(text="hello")]


@pytest.mark.asyncio
async def test_unknown_tool_returns_safe_error() -> None:
    result = await ToolRegistry([]).execute(
        ToolCall(id="call-1", name="missing", arguments={"secret": "value"})
    )

    assert result.output is None
    assert result.error is not None
    assert result.error.code == "tool_not_found"
    assert "secret" not in result.error.message


@pytest.mark.asyncio
async def test_invalid_arguments_do_not_execute_tool() -> None:
    tool = EchoTool()

    result = await ToolRegistry([tool]).execute(
        ToolCall(id="call-1", name="echo", arguments={"unexpected": "value"})
    )

    assert result.error is not None
    assert result.error.code == "invalid_arguments"
    assert tool.calls == []
    assert "unexpected" not in result.error.message


@pytest.mark.asyncio
async def test_tool_exception_returns_safe_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = await ToolRegistry([FailingTool()]).execute(
        ToolCall(id="call-1", name="failing", arguments={"text": "secret"})
    )

    assert result.error is not None
    assert result.error.code == "tool_execution_failed"
    assert "sensitive" not in result.error.message
    assert "secret" not in result.error.message
    assert caplog.records[-1].getMessage().startswith("agent.tool.execution_failed ")
    assert (
        "tool_name=failing error_type=RuntimeError" in caplog.records[-1].getMessage()
    )
    assert caplog.records[-1].error_type == "RuntimeError"
    assert "sensitive implementation detail" not in caplog.text
    assert "secret" not in caplog.text
