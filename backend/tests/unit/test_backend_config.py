from collections.abc import Iterator, Mapping
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import smeshariki_ai.config as config_module
from smeshariki_ai.agent import AgentConfig, LiteLLMProviderConfig
from smeshariki_ai.agent.prompts import (
    SystemPromptResourceError,
    load_system_prompt,
)
from smeshariki_ai.config import Config, load_config


class EnvironmentAccessForbidden(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise AssertionError(f"Unexpected process environment read: {key}")

    def __iter__(self) -> Iterator[str]:
        raise AssertionError("Unexpected process environment iteration")

    def __len__(self) -> int:
        raise AssertionError("Unexpected process environment size read")


def test_config_has_component_owned_nested_configs() -> None:
    config = load_config({"LLM_MODEL": "test/model"})

    assert set(Config.model_fields) == {"agent", "llm"}
    assert isinstance(config.agent, AgentConfig)
    assert isinstance(config.llm, LiteLLMProviderConfig)
    assert not hasattr(config_module, "ApplicationConfig")


def test_load_config_uses_agent_and_provider_defaults() -> None:
    config = load_config({"LLM_MODEL": "test/model"})

    assert config == Config(
        agent=AgentConfig(
            system_prompt=load_system_prompt(),
            max_iterations=4,
        ),
        llm=LiteLLMProviderConfig(model="test/model"),
    )


def test_load_config_reads_all_supported_values() -> None:
    config = load_config(
        {
            "AGENT_MAX_ITERATIONS": "2",
            "LLM_MODEL": "openai/test-model",
            "LLM_API_KEY": "private-api-key",
            "LLM_BASE_URL": "https://llm.example.test/v1",
            "LLM_TIMEOUT_SECONDS": "12.5",
            "LLM_NUM_RETRIES": "2",
        }
    )

    assert config.agent.system_prompt == load_system_prompt()
    assert config.agent.max_iterations == 2
    assert config.llm.model == "openai/test-model"
    assert config.llm.api_key is not None
    assert config.llm.api_key.get_secret_value() == "private-api-key"
    assert str(config.llm.base_url) == "https://llm.example.test/v1"
    assert config.llm.timeout_seconds == 12.5
    assert config.llm.num_retries == 2


def test_load_config_uses_versioned_system_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "load_system_prompt",
        lambda: "Versioned prompt",
    )

    config = load_config({"LLM_MODEL": "test/model"})

    assert config.agent.system_prompt == "Versioned prompt"


def test_load_config_does_not_override_system_prompt_from_environment() -> None:
    config = load_config(
        {
            "AGENT_SYSTEM_PROMPT": "Untracked deployment prompt",
            "LLM_MODEL": "test/model",
        }
    )

    assert config.agent.system_prompt == load_system_prompt()


def test_load_config_propagates_system_prompt_resource_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_to_load_prompt() -> str:
        raise SystemPromptResourceError("System prompt resource is empty.")

    monkeypatch.setattr(config_module, "load_system_prompt", fail_to_load_prompt)

    with pytest.raises(SystemPromptResourceError):
        load_config({"LLM_MODEL": "test/model"})


def test_load_config_normalizes_blank_optional_provider_values() -> None:
    config = load_config(
        {
            "LLM_MODEL": "test/model",
            "LLM_API_KEY": "   ",
            "LLM_BASE_URL": "",
        }
    )

    assert config.llm.api_key is None
    assert config.llm.base_url is None


@pytest.mark.parametrize(
    "environ",
    [
        {},
        {"LLM_MODEL": "test/model", "AGENT_MAX_ITERATIONS": "0"},
        {"LLM_MODEL": "test/model", "LLM_BASE_URL": "not-a-url"},
        {"LLM_MODEL": "test/model", "LLM_TIMEOUT_SECONDS": "0"},
        {"LLM_MODEL": "test/model", "LLM_NUM_RETRIES": "-1"},
    ],
    ids=[
        "missing-model",
        "invalid-iterations",
        "invalid-base-url",
        "invalid-timeout",
        "invalid-retries",
    ],
)
def test_load_config_rejects_invalid_environment(
    environ: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        load_config(environ)


def test_config_and_nested_configs_are_frozen_and_forbid_extra_fields() -> None:
    config = load_config({"LLM_MODEL": "test/model"})

    with pytest.raises(ValidationError):
        setattr(config, "agent", config.agent)
    with pytest.raises(ValidationError):
        setattr(config.agent, "max_iterations", 2)
    with pytest.raises(ValidationError):
        setattr(config.llm, "num_retries", 2)
    with pytest.raises(ValidationError):
        Config.model_validate(
            {
                "agent": config.agent,
                "llm": config.llm,
                "unexpected": True,
            }
        )


def test_config_representation_does_not_reveal_api_key() -> None:
    api_key = "secret-config-marker"

    config = load_config({"LLM_MODEL": "test/model", "LLM_API_KEY": api_key})

    assert api_key not in repr(config)
    assert api_key not in str(config)


def test_config_validation_error_does_not_reveal_api_key() -> None:
    api_key = "secret-validation-marker"

    with pytest.raises(ValidationError) as exc_info:
        load_config(
            {
                "LLM_MODEL": "test/model",
                "LLM_API_KEY": api_key,
                "LLM_TIMEOUT_SECONDS": "0",
            }
        )

    assert api_key not in str(exc_info.value)


def test_explicit_mapping_does_not_read_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "os",
        SimpleNamespace(environ=EnvironmentAccessForbidden()),
    )

    config = load_config({"LLM_MODEL": "explicit/model"})

    assert config.llm.model == "explicit/model"


def test_repeated_loads_create_independent_configs() -> None:
    first = load_config({"LLM_MODEL": "first/model"})
    second = load_config({"LLM_MODEL": "second/model"})
    expected_prompt = load_system_prompt()

    assert first is not second
    assert first.agent is not second.agent
    assert first.llm is not second.llm
    assert first.agent.system_prompt == expected_prompt
    assert first.llm.model == "first/model"
    assert second.agent.system_prompt == expected_prompt
    assert second.llm.model == "second/model"
