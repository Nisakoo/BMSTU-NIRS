import os
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from smeshariki_ai.agent import AgentConfig, LiteLLMProviderConfig
from smeshariki_ai.agent.prompts import load_system_prompt
from smeshariki_ai.auth import AuthConfig
from smeshariki_ai.cache import RedisConfig
from smeshariki_ai.db import DatabaseConfig
from smeshariki_ai.observability import LoggingConfig

__all__ = ["Config", "load_config"]


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent: AgentConfig
    llm: LiteLLMProviderConfig
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    auth: AuthConfig
    database: DatabaseConfig
    redis: RedisConfig


def load_config(environ: Mapping[str, str] | None = None) -> Config:
    source = os.environ if environ is None else environ
    agent_values: dict[str, Any] = {
        "system_prompt": load_system_prompt(),
        "max_iterations": 4,
    }

    if "AGENT_MAX_ITERATIONS" in source:
        agent_values["max_iterations"] = source["AGENT_MAX_ITERATIONS"]

    provider_values: dict[str, Any] = {}
    if "LLM_MODEL" in source:
        provider_values["model"] = source["LLM_MODEL"]
    for environment_name, field_name in (
        ("LLM_API_KEY", "api_key"),
        ("LLM_BASE_URL", "base_url"),
        ("LLM_TIMEOUT_SECONDS", "timeout_seconds"),
        ("LLM_NUM_RETRIES", "num_retries"),
    ):
        if environment_name in source and source[environment_name].strip():
            provider_values[field_name] = source[environment_name]

    logging_values: dict[str, Any] = {}
    for environment_name, field_name in (
        ("LOG_LEVEL", "level"),
        ("LOG_FORMAT", "format"),
    ):
        if environment_name in source:
            logging_values[field_name] = source[environment_name]

    auth_values: dict[str, Any] = {}
    for environment_name, field_name in (
        ("AUTH_JWT_SECRET", "jwt_secret"),
        ("AUTH_ACCESS_TTL_SECONDS", "access_ttl_seconds"),
        ("AUTH_REFRESH_TTL_SECONDS", "refresh_ttl_seconds"),
        ("AUTH_COOKIE_SECURE", "cookie_secure"),
    ):
        if environment_name in source:
            auth_values[field_name] = source[environment_name]

    database_values: dict[str, Any] = {}
    if "DATABASE_URL" in source:
        database_values["url"] = source["DATABASE_URL"]

    redis_values: dict[str, Any] = {}
    if "REDIS_URL" in source:
        redis_values["url"] = source["REDIS_URL"]

    return Config(
        agent=AgentConfig.model_validate(agent_values),
        llm=LiteLLMProviderConfig.model_validate(provider_values),
        logging=LoggingConfig.model_validate(logging_values),
        auth=AuthConfig.model_validate(auth_values),
        database=DatabaseConfig.model_validate(database_values),
        redis=RedisConfig.model_validate(redis_values),
    )
