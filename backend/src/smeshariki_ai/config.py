import os
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from smeshariki_ai.agent import AgentConfig, LiteLLMProviderConfig

__all__ = ["Config", "load_config"]


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent: AgentConfig
    llm: LiteLLMProviderConfig


def load_config(environ: Mapping[str, str] | None = None) -> Config:
    source = os.environ if environ is None else environ
    agent_values: dict[str, Any] = {
        "system_prompt": "You are a helpful Smeshariki assistant.",
        "max_iterations": 4,
    }

    if "AGENT_SYSTEM_PROMPT" in source:
        agent_values["system_prompt"] = source["AGENT_SYSTEM_PROMPT"]
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

    return Config(
        agent=AgentConfig.model_validate(agent_values),
        llm=LiteLLMProviderConfig.model_validate(provider_values),
    )
