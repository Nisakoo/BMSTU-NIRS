import pytest
from pydantic import ValidationError

from smeshariki_ai.agent.providers import LiteLLMProviderConfig


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"model": "   "},
        {"model": "test/model", "api_key": ""},
        {"model": "test/model", "base_url": "not-a-url"},
        {"model": "test/model", "timeout_seconds": 0},
        {"model": "test/model", "num_retries": -1},
        {"model": "test/model", "unknown": "value"},
        {"model": "test/model", "temperature": -0.1},
        {"model": "test/model", "temperature": 2.1},
        {"model": "test/model", "thinking": "not-a-bool"},
        {"model": "openai/test-model", "thinking": True},
    ],
    ids=[
        "missing-model",
        "blank-model",
        "blank-api-key",
        "invalid-base-url",
        "non-positive-timeout",
        "negative-retries",
        "extra-field",
        "temperature-below-range",
        "temperature-above-range",
        "invalid-thinking",
        "thinking-requires-deepseek",
    ],
)
def test_litellm_provider_config_rejects_invalid_values(
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        LiteLLMProviderConfig.model_validate(values)


def test_litellm_provider_config_validation_error_hides_api_key() -> None:
    with pytest.raises(ValidationError) as captured:
        LiteLLMProviderConfig(
            model="openai/test-model",
            api_key="private-api-key",
            timeout_seconds=0,
        )

    assert "private-api-key" not in str(captured.value)
