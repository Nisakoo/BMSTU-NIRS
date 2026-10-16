from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

MIN_JWT_SECRET_BYTES = 32


class AuthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    jwt_secret: SecretStr
    access_ttl_seconds: int = Field(default=15 * 60, gt=0)
    refresh_ttl_seconds: int = Field(default=30 * 24 * 60 * 60, gt=0)
    cookie_secure: bool = False
    issuer: str = "smeshariki-ai"

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
        return value
