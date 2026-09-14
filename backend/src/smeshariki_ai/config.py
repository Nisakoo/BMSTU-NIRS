import os
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApplicationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_system_prompt: str = "You are a helpful Smeshariki assistant."
    agent_max_iterations: int = Field(default=4, gt=0)


def load_config(environ: Mapping[str, str] | None = None) -> ApplicationConfig:
    source = os.environ if environ is None else environ
    values: dict[str, Any] = {}

    if "AGENT_SYSTEM_PROMPT" in source:
        values["agent_system_prompt"] = source["AGENT_SYSTEM_PROMPT"]
    if "AGENT_MAX_ITERATIONS" in source:
        values["agent_max_iterations"] = source["AGENT_MAX_ITERATIONS"]

    return ApplicationConfig.model_validate(values)
