import importlib
import logging
import sys
from typing import Any

import httpx
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
from smeshariki_ai.auth import (
    AuthConfig,
    AuthService,
    InMemoryRefreshSessionStore,
    InMemoryTokenBlacklist,
    InMemoryUserStore,
)
from smeshariki_ai.bootstrap import (
    build_agent_service,
    configure_logging,
    create_application,
)
from smeshariki_ai.cache import RedisAttemptLimiter, RedisConfig
from smeshariki_ai.config import Config
from smeshariki_ai.db import DatabaseConfig
from smeshariki_ai.observability import LoggingConfig


def make_config() -> Config:
    return Config(
        agent=AgentConfig(system_prompt="Test prompt", max_iterations=2),
        llm=LiteLLMProviderConfig(model="test/model"),
        auth=AuthConfig(jwt_secret="test-secret-with-at-least-32-bytes!!"),
        database=DatabaseConfig(url="postgresql+asyncpg://app:app@127.0.0.1:1/app"),
        redis=RedisConfig(url="redis://127.0.0.1:1/0"),
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
    assert [
        definition.name for definition in service._agent._tool_registry.definitions
    ] == ["get_context"]


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
        configure_logging(LoggingConfig())
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


async def test_create_application_wires_auth_and_closes_infrastructure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config()
    closed: list[str] = []
    received: dict[str, object] = {}

    class FakeEngine:
        async def dispose(self) -> None:
            closed.append("engine")

    class FakeRedis:
        async def aclose(self) -> None:
            closed.append("redis")

    def fake_engine(value: DatabaseConfig) -> FakeEngine:
        received["database"] = value
        return FakeEngine()

    def fake_redis(value: RedisConfig) -> FakeRedis:
        received["redis"] = value
        return FakeRedis()

    monkeypatch.setattr(bootstrap_module, "create_engine", fake_engine)
    monkeypatch.setattr(bootstrap_module, "create_redis", fake_redis)

    app = create_application(config, llm_provider=FakeLLMProvider())

    assert received == {"database": config.database, "redis": config.redis}
    assert isinstance(app.state.auth_service, AuthService)
    assert isinstance(app.state.auth_service._limiter, RedisAttemptLimiter)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/users/me")
    assert response.json() == {"error": "unauthorized"}
    async with app.router.lifespan_context(app):
        assert closed == []
    assert closed == ["engine", "redis"]


def test_create_application_accepts_explicit_auth_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config()
    auth_service = AuthService(
        users=InMemoryUserStore(),
        sessions=InMemoryRefreshSessionStore(),
        blacklist=InMemoryTokenBlacklist(),
        config=config.auth,
    )

    def reject(value: object) -> None:
        pytest.fail("Infrastructure must not be created for an explicit service")

    monkeypatch.setattr(bootstrap_module, "create_engine", reject)
    monkeypatch.setattr(bootstrap_module, "create_redis", reject)

    app = create_application(
        config, llm_provider=FakeLLMProvider(), auth_service=auth_service
    )

    assert app.state.auth_service is auth_service
