import pytest
from pydantic import ValidationError

from smeshariki_ai.agent.providers import LiteLLMProviderConfig


def test_litellm_provider_config_uses_safe_defaults() -> None:
    config = LiteLLMProviderConfig(model="openai/test-model")

    assert config.model == "openai/test-model"
    assert config.api_key is None
    assert config.base_url is None
    assert config.timeout_seconds == 60
    assert config.num_retries == 0


def test_litellm_provider_config_accepts_connection_settings() -> None:
    config = LiteLLMProviderConfig(
        model="openai/test-model",
        api_key="private-api-key",
        base_url="https://llm.example.test/v1",
        timeout_seconds=12.5,
        num_retries=2,
    )

    assert config.api_key is not None
    assert config.api_key.get_secret_value() == "private-api-key"
    assert str(config.base_url) == "https://llm.example.test/v1"
    assert config.timeout_seconds == 12.5
    assert config.num_retries == 2
    assert "private-api-key" not in repr(config)
    assert "private-api-key" not in str(config)


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
    ],
    ids=[
        "missing-model",
        "blank-model",
        "blank-api-key",
        "invalid-base-url",
        "non-positive-timeout",
        "negative-retries",
        "extra-field",
    ],
)
def test_litellm_provider_config_rejects_invalid_values(
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        LiteLLMProviderConfig.model_validate(values)


def test_litellm_provider_config_is_frozen() -> None:
    config = LiteLLMProviderConfig(model="openai/test-model")

    with pytest.raises(ValidationError):
        config.model = "openai/other-model"


def test_litellm_provider_config_validation_error_hides_api_key() -> None:
    with pytest.raises(ValidationError) as captured:
        LiteLLMProviderConfig(
            model="openai/test-model",
            api_key="private-api-key",
            timeout_seconds=0,
        )

    assert "private-api-key" not in str(captured.value)
