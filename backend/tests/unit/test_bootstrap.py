import importlib
import logging
import sys
from typing import Any

import pytest
from fastapi import FastAPI

import smeshariki_ai.bootstrap as bootstrap_module
import smeshariki_ai.config as config_module
from smeshariki_ai.agent import (
    AgentConfig,
    FakeLLMProvider,
    LiteLLMProviderConfig,
)
from smeshariki_ai.application import AgentService, InMemoryDialogEventBroker
from smeshariki_ai.bootstrap import (
    build_agent_service,
    configure_logging,
    create_application,
)
from smeshariki_ai.config import Config


def make_config() -> Config:
    return Config(
        agent=AgentConfig(system_prompt="Test prompt", max_iterations=2),
        llm=LiteLLMProviderConfig(model="test/model"),
    )


def test_bootstrap_builds_service_with_explicit_provider() -> None:
    config = make_config()
    provider = FakeLLMProvider()

    service = build_agent_service(config, llm_provider=provider)
    app = create_application(config, llm_provider=provider)

    assert isinstance(service, AgentService)
    assert isinstance(service._event_broker, InMemoryDialogEventBroker)
    assert isinstance(app, FastAPI)
    assert app.title == "smeshariki-ai"
    assert isinstance(app.state.agent_service, AgentService)


def test_bootstrap_passes_exact_component_configs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config()
    provider = FakeLLMProvider()
    received_configs: list[LiteLLMProviderConfig] = []
    received_agent_arguments: list[dict[str, Any]] = []

    def build_provider(value: LiteLLMProviderConfig) -> FakeLLMProvider:
        received_configs.append(value)
        return provider

    def build_agent(**kwargs: Any) -> object:
        received_agent_arguments.append(kwargs)
        return object()

    monkeypatch.setattr(bootstrap_module, "LiteLLMProvider", build_provider)
    monkeypatch.setattr(bootstrap_module, "Agent", build_agent)

    service = build_agent_service(config)

    assert isinstance(service, AgentService)
    assert received_configs == [config.llm]
    assert received_configs[0] is config.llm
    assert received_agent_arguments[0]["config"] is config.agent
    assert received_agent_arguments[0]["llm_provider"] is provider


def test_explicit_provider_does_not_construct_litellm_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config()
    provider = FakeLLMProvider()
    received_agent_arguments: list[dict[str, Any]] = []

    def reject_provider_construction(value: LiteLLMProviderConfig) -> None:
        pytest.fail(f"Unexpected LiteLLMProvider construction for {value.model}")

    def build_agent(**kwargs: Any) -> object:
        received_agent_arguments.append(kwargs)
        return object()

    monkeypatch.setattr(
        bootstrap_module,
        "LiteLLMProvider",
        reject_provider_construction,
    )
    monkeypatch.setattr(bootstrap_module, "Agent", build_agent)

    service = build_agent_service(config, llm_provider=provider)

    assert isinstance(service, AgentService)
    assert received_agent_arguments[0]["config"] is config.agent
    assert received_agent_arguments[0]["llm_provider"] is provider


def test_create_application_requires_config() -> None:
    with pytest.raises(TypeError):
        create_application()  # type: ignore[call-arg]


def test_configure_logging_enables_application_info_events() -> None:
    application_logger = logging.getLogger("smeshariki_ai")
    original_level = application_logger.level
    application_logger.setLevel(logging.WARNING)

    try:
        configure_logging()
        assert application_logger.level == logging.INFO
    finally:
        application_logger.setLevel(original_level)


def test_main_loads_config_once_and_passes_it_to_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config()
    expected_app = FastAPI()
    load_calls = 0
    received_configs: list[Config] = []

    def load_config() -> Config:
        nonlocal load_calls
        load_calls += 1
        return config

    def create_application(value: Config) -> FastAPI:
        received_configs.append(value)
        return expected_app

    monkeypatch.setattr(config_module, "load_config", load_config)
    monkeypatch.setattr(bootstrap_module, "create_application", create_application)
    monkeypatch.delitem(sys.modules, "smeshariki_ai.main", raising=False)

    try:
        main_module = importlib.import_module("smeshariki_ai.main")
    finally:
        sys.modules.pop("smeshariki_ai.main", None)

    assert main_module.app is expected_app
    assert load_calls == 1
    assert received_configs == [config]
    assert received_configs[0] is config
