from typing import Any

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from smeshariki_ai.agent.models import NonEmptyString


class LiteLLMProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: NonEmptyString
    api_key: SecretStr | None = None
    base_url: AnyHttpUrl | None = None
    timeout_seconds: float = Field(default=60, gt=0)
    num_retries: int = Field(default=0, ge=0)
    temperature: float = Field(default=0.8, ge=0, le=2)
    thinking: bool = False

    @field_validator("api_key", mode="before")
    @classmethod
    def reject_blank_api_key(cls, value: Any) -> Any:
        if value is None:
            return value
        secret = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(secret, str) and not secret.strip():
            raise ValueError("API key must not be blank.")
        return value

    @model_validator(mode="after")
    def require_deepseek_for_thinking(self) -> "LiteLLMProviderConfig":
        if self.thinking and not self.model.startswith("deepseek/"):
            raise ValueError("Thinking is supported only for DeepSeek models.")
        return self
