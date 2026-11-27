import pytest
from pydantic import ValidationError

from smeshariki_ai.agent.models import (
    AgentConfig,
    LLMResponse,
    LLMTextDelta,
    UserRequest,
)


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


def test_llm_text_delta_accepts_whitespace_but_rejects_empty_content() -> None:
    assert LLMTextDelta(content=" \n").content == " \n"

    with pytest.raises(ValidationError):
        LLMTextDelta(content="")
