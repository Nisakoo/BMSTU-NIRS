from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

MIN_JWT_SECRET_BYTES = 32
# Prefix of the placeholder convention in docker/.env.example.
PLACEHOLDER_SECRET_PREFIX = "replace-with-"


class RateLimitConfig(BaseModel):
    """Fixed-window limits of login and registration attempts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    login_failures: int = Field(default=5, gt=0)
    login_failure_window_seconds: int = Field(default=15 * 60, gt=0)
    login_per_ip: int = Field(default=30, gt=0)
    login_per_ip_window_seconds: int = Field(default=60, gt=0)
    register_per_ip: int = Field(default=10, gt=0)
    register_per_ip_window_seconds: int = Field(default=60 * 60, gt=0)


class AuthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    jwt_secret: SecretStr
    access_ttl_seconds: int = Field(default=15 * 60, gt=0)
    refresh_ttl_seconds: int = Field(default=30 * 24 * 60 * 60, gt=0)
    cookie_secure: bool = False
    issuer: str = "smeshariki-ai"
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def require_long_secret(cls, value: Any) -> Any:
        secret = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not isinstance(secret, str) or (
            len(secret.encode("utf-8")) < MIN_JWT_SECRET_BYTES
        ):
            raise ValueError(
                f"JWT secret must contain at least {MIN_JWT_SECRET_BYTES} bytes."
            )
        if secret.startswith(PLACEHOLDER_SECRET_PREFIX):
            raise ValueError("JWT secret must not be a placeholder value.")
        return value
