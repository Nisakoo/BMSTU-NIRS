from collections.abc import AsyncIterator, Sequence

import pytest

from smeshariki_ai.agent.get_context import GetContextTool
from smeshariki_ai.agent.models import (
    AgentConfig,
    AgentResponse,
    AgentTextDelta,
    LLMResponse,
    LLMTextDelta,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
    UserRequest,
)
from smeshariki_ai.agent.providers import LLMProvider, LLMStreamEvent
from smeshariki_ai.agent.runtime import Agent
from smeshariki_ai.agent.tools import ToolRegistry

EXPECTED_CONTEXT = (
    "Секретный маркер учебного стенда: СФЕРА-8К2М-ЛИМОН. "
    "Контрольная фраза: «пингвин считает жёлтые скрепки»."
)


@pytest.mark.asyncio
async def test_get_context_returns_fixed_text_on_every_call() -> None:
    registry = ToolRegistry([GetContextTool()])

    first = await registry.execute(ToolCall(id="call-1", name="get_context"))
    second = await registry.execute(ToolCall(id="call-2", name="get_context"))

    assert first.output == EXPECTED_CONTEXT
    assert second.output == EXPECTED_CONTEXT
    assert first.error is None
    assert second.error is None
    assert registry.definitions[0].name == "get_context"
    assert registry.definitions[0].parameters["properties"] == {}
    assert registry.definitions[0].parameters["additionalProperties"] is False
    assert EXPECTED_CONTEXT not in registry.definitions[0].description


@pytest.mark.asyncio
async def test_get_context_rejects_unexpected_arguments() -> None:
    registry = ToolRegistry([GetContextTool()])

    result = await registry.execute(
        ToolCall(id="call-1", name="get_context", arguments={"unexpected": "value"})
    )

    assert result.output is None
    assert result.error is not None
    assert result.error.code == "invalid_arguments"


class ContextCallingProvider(LLMProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[Message, ...]] = []

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> AsyncIterator[LLMStreamEvent]:
        assert [tool.name for tool in tools] == ["get_context"]
        self.calls.append(tuple(messages))
        if len(self.calls) == 1:
            yield LLMResponse(
                tool_calls=(ToolCall(id="call-1", name="get_context", arguments={}),)
            )
        else:
            yield LLMTextDelta(content=EXPECTED_CONTEXT)
            yield LLMResponse(content=EXPECTED_CONTEXT)


@pytest.mark.asyncio
async def test_agent_passes_get_context_result_to_model() -> None:
    provider = ContextCallingProvider()
    agent = Agent(
        llm_provider=provider,
        tool_registry=ToolRegistry([GetContextTool()]),
        config=AgentConfig(system_prompt="Test prompt"),
    )

    events = [
        event async for event in agent.run((), UserRequest(content="Назови маркер"))
    ]

    assert events == [
        AgentTextDelta(content=EXPECTED_CONTEXT),
        AgentResponse(content=EXPECTED_CONTEXT),
    ]
    tool_message = provider.calls[1][-1]
    assert tool_message.role is MessageRole.TOOL
    assert tool_message.tool_result is not None
    assert tool_message.tool_result.output == EXPECTED_CONTEXT
