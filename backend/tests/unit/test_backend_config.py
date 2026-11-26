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
from smeshariki_ai.auth import AuthConfig, RateLimitConfig
from smeshariki_ai.cache import RedisConfig
from smeshariki_ai.config import Config, load_config
from smeshariki_ai.db import DatabaseConfig
from smeshariki_ai.rag.config import RagConfig
from smeshariki_ai.speech import CephS3Config, SpeechConfig

JWT_SECRET = "test-secret-with-at-least-32-bytes!!"
DATABASE_URL = "postgresql+asyncpg://app:db-password@postgres:5432/app"
REDIS_URL = "redis://:redis-password@redis:6379/0"
BASE_ENV = {
    "AUTH_JWT_SECRET": JWT_SECRET,
    "DATABASE_URL": DATABASE_URL,
    "REDIS_URL": REDIS_URL,
}


class EnvironmentAccessForbidden(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise AssertionError(f"Unexpected process environment read: {key}")

    def __iter__(self) -> Iterator[str]:
        raise AssertionError("Unexpected process environment iteration")

    def __len__(self) -> int:
        raise AssertionError("Unexpected process environment size read")


def test_config_has_component_owned_nested_configs() -> None:
    config = load_config({**BASE_ENV, "LLM_MODEL": "test/model"})

    assert set(Config.model_fields) == {
        "agent",
        "llm",
        "logging",
        "auth",
        "database",
        "redis",
        "speech",
        "ceph",
        "rag",
    }
    assert isinstance(config.agent, AgentConfig)
    assert isinstance(config.llm, LiteLLMProviderConfig)
    assert isinstance(config.rag, RagConfig)
    assert not hasattr(config_module, "ApplicationConfig")


def test_load_config_uses_agent_and_provider_defaults() -> None:
    config = load_config({**BASE_ENV, "LLM_MODEL": "test/model"})

    assert config == Config(
        agent=AgentConfig(
            system_prompt=load_system_prompt(),
            max_iterations=4,
        ),
        llm=LiteLLMProviderConfig(model="test/model"),
        auth=AuthConfig(jwt_secret=JWT_SECRET),
        database=DatabaseConfig(url=DATABASE_URL),
        redis=RedisConfig(url=REDIS_URL),
        speech=SpeechConfig(),
        ceph=CephS3Config(),
    )
    assert config.logging.level == "INFO"
    assert config.logging.format == "human"


def test_load_config_reads_ceph_options() -> None:
    config = load_config(
        {
            **BASE_ENV,
            "LLM_MODEL": "test/model",
            "CEPH_S3_ENDPOINT": "http://ceph:7480/",
            "CEPH_S3_BUCKET": "audio-test",
            "CEPH_S3_ACCESS_KEY": "access",
            "CEPH_S3_SECRET_KEY": "secret",
            "CEPH_S3_REGION": "region",
            "CEPH_S3_PREFIX": "prefix",
        }
    )

    assert config.ceph.endpoint == "http://ceph:7480"
    assert config.ceph.bucket == "audio-test"
    assert config.ceph.access_key == "access"
    assert config.ceph.secret_key.get_secret_value() == "secret"
    assert config.ceph.region == "region"
    assert config.ceph.prefix == "prefix"


def test_load_config_reads_speech_options() -> None:
    config = load_config(
        {
            **BASE_ENV,
            "LLM_MODEL": "test/model",
            "SPEECH_ENABLED": "false",
            "SPEECH_VOICE": "aidar",
            "SPEECH_SPEED": "1.1",
            "SPEECH_MAX_CONCURRENCY": "2",
            "SPEECH_MAX_TEXT_CHARS": "12345",
            "SPEECH_MODEL_PATH": "/tmp/v5_ru.pt",
        }
    )

    assert config.speech == SpeechConfig(
        enabled=False,
        voice="aidar",
        speed=1.1,
        max_concurrency=2,
        max_text_chars=12_345,
        model_path="/tmp/v5_ru.pt",
    )


def test_load_config_uses_speech_defaults() -> None:
    assert load_config({**BASE_ENV, "LLM_MODEL": "test/model"}).speech == SpeechConfig()


def test_query_expansion_is_off_by_default() -> None:
    config = load_config({**BASE_ENV, "LLM_MODEL": "test/model"})

    assert config.rag == RagConfig()
    assert config.rag.query_expansion_enabled is False


def test_query_expansion_flag_is_read_from_the_environment() -> None:
    config = load_config(
        {
            **BASE_ENV,
            "LLM_MODEL": "test/model",
            "RAG_QUERY_EXPANSION_ENABLED": "true",
        }
    )

    assert config.rag.query_expansion_enabled is True


def test_lore_context_settings_have_defaults() -> None:
    config = load_config({**BASE_ENV, "LLM_MODEL": "test/model"})

    assert config.rag.lore_retrieval_k == 10
    assert config.rag.lore_max_passages == 3
    assert config.rag.lore_max_chars == 1600
    assert config.rag.lore_min_score == 2.0
    assert config.rag.query_expansion_mode == "replace"


def test_lore_context_settings_are_read_from_the_environment() -> None:
    config = load_config(
        {
            **BASE_ENV,
            "LLM_MODEL": "test/model",
            "RAG_LORE_RETRIEVAL_K": "7",
            "RAG_LORE_MAX_PASSAGES": "2",
            "RAG_LORE_MAX_CHARS": "900",
            "RAG_LORE_MIN_SCORE": "0.5",
            "RAG_QUERY_EXPANSION_MODE": "append",
        }
    )

    assert config.rag.lore_retrieval_k == 7
    assert config.rag.lore_max_passages == 2
    assert config.rag.lore_max_chars == 900
    assert config.rag.lore_min_score == 0.5
    assert config.rag.query_expansion_mode == "append"


@pytest.mark.parametrize(
    "change",
    [
        {"SPEECH_ENABLED": "maybe"},
        {"SPEECH_VOICE": "unknown"},
        {"SPEECH_SPEED": "0.4"},
        {"SPEECH_MAX_CONCURRENCY": "0"},
        {"SPEECH_MAX_TEXT_CHARS": "abc"},
        {"SPEECH_MODEL_PATH": " "},
        {"CEPH_S3_ENDPOINT": "not-a-url"},
        {"CEPH_S3_BUCKET": " "},
        {"CEPH_S3_SECRET_KEY": ""},
    ],
)
def test_load_config_rejects_invalid_speech_options(
    change: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        load_config({**BASE_ENV, "LLM_MODEL": "test/model", **change})


def test_load_config_reads_logging_options() -> None:
    config = load_config(
        {
            **BASE_ENV,
            "LLM_MODEL": "test/model",
            "LOG_LEVEL": "DEBUG",
            "LOG_FORMAT": "json",
        }
    )

    assert config.logging.level == "DEBUG"
    assert config.logging.format == "json"


@pytest.mark.parametrize("name,value", [("LOG_LEVEL", "TRACE"), ("LOG_FORMAT", "xml")])
def test_load_config_rejects_invalid_logging_options(name: str, value: str) -> None:
    with pytest.raises(ValidationError):
        load_config({**BASE_ENV, "LLM_MODEL": "test/model", name: value})


def test_load_config_reads_all_supported_values() -> None:
    config = load_config(
        {
            **BASE_ENV,
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

    config = load_config({**BASE_ENV, "LLM_MODEL": "test/model"})

    assert config.agent.system_prompt == "Versioned prompt"


def test_load_config_ignores_unsupported_environment_values() -> None:
    config = load_config(
        {
            **BASE_ENV,
            "UNSUPPORTED_AGENT_PROMPT": "Untracked deployment prompt",
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
        load_config({**BASE_ENV, "LLM_MODEL": "test/model"})


def test_load_config_reads_generation_options() -> None:
    config = load_config(
        {
            **BASE_ENV,
            "LLM_MODEL": "deepseek/deepseek-flash",
            "LLM_TEMPERATURE": "1.1",
            "LLM_THINKING": "true",
        }
    )

    assert config.llm.temperature == 1.1
    assert config.llm.thinking is True


def test_load_config_normalizes_blank_optional_provider_values() -> None:
    config = load_config(
        {
            **BASE_ENV,
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
        {**BASE_ENV, "LLM_MODEL": "test/model", "AGENT_MAX_ITERATIONS": "0"},
        {**BASE_ENV, "LLM_MODEL": "test/model", "LLM_BASE_URL": "not-a-url"},
        {**BASE_ENV, "LLM_MODEL": "test/model", "LLM_TIMEOUT_SECONDS": "0"},
        {**BASE_ENV, "LLM_MODEL": "test/model", "LLM_NUM_RETRIES": "-1"},
        {**BASE_ENV, "LLM_MODEL": "test/model", "LLM_TEMPERATURE": "2.1"},
        {**BASE_ENV, "LLM_MODEL": "test/model", "LLM_TEMPERATURE": "-0.1"},
        {**BASE_ENV, "LLM_MODEL": "test/model", "LLM_THINKING": "maybe"},
        {**BASE_ENV, "LLM_MODEL": "openai/test-model", "LLM_THINKING": "true"},
    ],
    ids=[
        "missing-model",
        "invalid-iterations",
        "invalid-base-url",
        "invalid-timeout",
        "invalid-retries",
        "temperature-above-range",
        "temperature-below-range",
        "invalid-thinking",
        "thinking-requires-deepseek",
    ],
)
def test_load_config_rejects_invalid_environment(
    environ: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        load_config(environ)


def test_config_and_nested_configs_are_frozen_and_forbid_extra_fields() -> None:
    config = load_config({**BASE_ENV, "LLM_MODEL": "test/model"})

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

    config = load_config(
        {**BASE_ENV, "LLM_MODEL": "test/model", "LLM_API_KEY": api_key}
    )

    assert api_key not in repr(config)
    assert api_key not in str(config)


def test_config_validation_error_does_not_reveal_api_key() -> None:
    api_key = "secret-validation-marker"

    with pytest.raises(ValidationError) as exc_info:
        load_config(
            {
                **BASE_ENV,
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

    config = load_config({**BASE_ENV, "LLM_MODEL": "explicit/model"})

    assert config.llm.model == "explicit/model"


def test_repeated_loads_create_independent_configs() -> None:
    first = load_config({**BASE_ENV, "LLM_MODEL": "first/model"})
    second = load_config({**BASE_ENV, "LLM_MODEL": "second/model"})
    expected_prompt = load_system_prompt()

    assert first is not second
    assert first.agent is not second.agent
    assert first.llm is not second.llm
    assert first.agent.system_prompt == expected_prompt
    assert first.llm.model == "first/model"
    assert second.agent.system_prompt == expected_prompt
    assert second.llm.model == "second/model"


def test_load_config_reads_auth_database_and_redis_values() -> None:
    config = load_config(
        {
            **BASE_ENV,
            "LLM_MODEL": "test/model",
            "AUTH_ACCESS_TTL_SECONDS": "60",
            "AUTH_REFRESH_TTL_SECONDS": "3600",
            "AUTH_COOKIE_SECURE": "true",
        }
    )

    assert config.auth.jwt_secret.get_secret_value() == JWT_SECRET
    assert config.auth.access_ttl_seconds == 60
    assert config.auth.refresh_ttl_seconds == 3600
    assert config.auth.cookie_secure is True
    assert config.database.url.get_secret_value() == DATABASE_URL
    assert config.redis.url.get_secret_value() == REDIS_URL


def test_load_config_reads_rate_limit_values() -> None:
    config = load_config(
        {
            **BASE_ENV,
            "LLM_MODEL": "test/model",
            "AUTH_LOGIN_MAX_FAILURES": "3",
            "AUTH_LOGIN_FAILURE_WINDOW_SECONDS": "120",
            "AUTH_LOGIN_MAX_PER_IP": "7",
            "AUTH_LOGIN_PER_IP_WINDOW_SECONDS": "30",
            "AUTH_REGISTER_MAX_PER_IP": "2",
            "AUTH_REGISTER_PER_IP_WINDOW_SECONDS": "600",
        }
    )

    assert config.auth.rate_limit == RateLimitConfig(
        login_failures=3,
        login_failure_window_seconds=120,
        login_per_ip=7,
        login_per_ip_window_seconds=30,
        register_per_ip=2,
        register_per_ip_window_seconds=600,
    )


def test_load_config_uses_rate_limit_defaults() -> None:
    config = load_config({**BASE_ENV, "LLM_MODEL": "test/model"})

    assert config.auth.rate_limit == RateLimitConfig()


def test_load_config_uses_auth_defaults() -> None:
    config = load_config({**BASE_ENV, "LLM_MODEL": "test/model"})

    assert config.auth.access_ttl_seconds == 900
    assert config.auth.refresh_ttl_seconds == 30 * 24 * 60 * 60
    assert config.auth.cookie_secure is False


@pytest.mark.parametrize(
    "change",
    [
        {"AUTH_JWT_SECRET": None},
        {"AUTH_JWT_SECRET": "short-secret-marker"},
        {"AUTH_JWT_SECRET": "replace-with-secret-marker-at-least-32-bytes"},
        {"DATABASE_URL": None},
        {"DATABASE_URL": "mysql://user:secret-db-marker@db/app"},
        {"REDIS_URL": None},
        {"REDIS_URL": "http://:secret-redis-marker@redis"},
        {"AUTH_ACCESS_TTL_SECONDS": "0"},
        {"AUTH_REFRESH_TTL_SECONDS": "abc"},
        {"AUTH_COOKIE_SECURE": "maybe"},
        {"AUTH_LOGIN_MAX_FAILURES": "0"},
        {"AUTH_REGISTER_PER_IP_WINDOW_SECONDS": "abc"},
    ],
)
def test_load_config_rejects_invalid_auth_environment(
    change: dict[str, str | None],
) -> None:
    environ = {**BASE_ENV, "LLM_MODEL": "test/model", **change}
    environ = {name: value for name, value in environ.items() if value is not None}

    with pytest.raises(ValidationError) as error:
        load_config(environ)

    for marker in (
        "short-secret-marker",
        "replace-with-secret-marker",
        "secret-db-marker",
        "secret-redis-marker",
    ):
        assert marker not in str(error.value)


def test_config_representation_does_not_reveal_auth_secrets() -> None:
    text = repr(load_config({**BASE_ENV, "LLM_MODEL": "test/model"}))

    for secret in (JWT_SECRET, "db-password", "redis-password"):
        assert secret not in text
