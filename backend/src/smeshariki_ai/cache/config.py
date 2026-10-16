from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class RedisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    # The URL may contain a password, so it is kept out of repr and errors.
    url: SecretStr
    timeout_seconds: float = Field(default=2, gt=0)

    @field_validator("url")
    @classmethod
    def require_redis_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("redis://", "rediss://")):
            raise ValueError("Redis URL must use the redis or rediss scheme.")
        return value
