from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

LOGIN_PATTERN = r"^[A-Za-z0-9_.-]{3,32}$"

Login = Annotated[str, StringConstraints(pattern=LOGIN_PATTERN)]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class Role(StrEnum):
    USER = "user"
    ADMIN = "admin"


class Credentials(BaseModel):
    """Login and password accepted from a client; no other fields are allowed."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    login: Login
    password: Password


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    login: str
    role: Role


@dataclass(frozen=True, slots=True)
class UserWithPassword:
    user: User
    password_hash: str


@dataclass(frozen=True, slots=True)
class RefreshSession:
    id: UUID
    user_id: UUID
    family_id: UUID
    token_hash: bytes
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    replaced_by: UUID | None = None


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: UUID
    role: Role
    jti: str
    session_id: UUID
    family_id: UUID
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


@dataclass(frozen=True, slots=True)
class AuthResult:
    user: User
    tokens: IssuedTokens


class AuthError(Exception):
    """Base class for safe authentication errors without request details."""


class LoginTakenError(AuthError):
    def __init__(self) -> None:
        super().__init__("Login is already taken.")


class InvalidCredentialsError(AuthError):
    def __init__(self) -> None:
        super().__init__("Invalid login or password.")


class UnauthorizedError(AuthError):
    def __init__(self) -> None:
        super().__init__("Authentication required.")


class AuthUnavailableError(AuthError):
    def __init__(self) -> None:
        super().__init__("Authentication storage is unavailable.")


class TooManyAttemptsError(AuthError):
    """A rate limit was hit; ``limit`` names it and carries no request data."""

    def __init__(self, limit: str, retry_after: int) -> None:
        super().__init__("Too many attempts.")
        self.limit = limit
        self.retry_after = retry_after
