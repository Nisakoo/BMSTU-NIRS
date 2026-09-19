import pytest
from pydantic import ValidationError

from smeshariki_ai.agent.models import (
    AgentConfig,
    LLMResponse,
    LLMTextDelta,
    Message,
    MessageRole,
    ToolDefinition,
    UserRequest,
)
from smeshariki_ai.agent.providers import FakeLLMProvider


def test_agent_config_uses_four_iterations_by_default() -> None:
    config = AgentConfig(system_prompt="You are a test agent.")

    assert config.max_iterations == 4


def test_agent_config_rejects_non_positive_iteration_limit() -> None:
    with pytest.raises(ValidationError):
        AgentConfig(system_prompt="You are a test agent.", max_iterations=0)


def test_user_request_rejects_blank_content() -> None:
    with pytest.raises(ValidationError):
        UserRequest(content="   ")


def test_llm_response_distinguishes_empty_text_from_missing_text() -> None:
    empty_response = LLMResponse(content="")
    missing_response = LLMResponse()

    assert empty_response.content == ""
    assert missing_response.content is None


@pytest.mark.asyncio
async def test_fake_llm_provider_exposes_only_successful_empty_stream() -> None:
    provider = FakeLLMProvider()
    messages = (Message(role=MessageRole.USER, content="Кто такой Крош?"),)
    tools = (
        ToolDefinition(
            name="search_knowledge",
            description="Search the knowledge base.",
            parameters={"type": "object", "properties": {}},
        ),
    )

    events = [event async for event in provider.stream(messages, tools)]

    assert events == [LLMResponse(content="", tool_calls=())]
    assert not hasattr(provider, "generate")
    assert messages[0].content == "Кто такой Крош?"


def test_llm_text_delta_accepts_whitespace_but_rejects_empty_content() -> None:
    assert LLMTextDelta(content=" \n").content == " \n"

    with pytest.raises(ValidationError):
        LLMTextDelta(content="")
