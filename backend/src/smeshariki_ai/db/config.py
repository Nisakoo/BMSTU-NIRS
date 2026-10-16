from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class DatabaseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    # The URL contains credentials, so it is kept out of repr and errors.
    url: SecretStr
    pool_size: int = Field(default=5, gt=0)

    @field_validator("url")
    @classmethod
    def require_asyncpg_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError("Database URL must use the postgresql+asyncpg scheme.")
        return value
