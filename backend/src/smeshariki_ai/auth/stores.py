"""Storage contracts of the authentication service.

Adapters raise ``AuthUnavailableError`` when their backing infrastructure fails,
so the service and HTTP layer can fail closed without knowing the adapter.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from smeshariki_ai.auth.models import RefreshSession, Role, User, UserWithPassword


class UserStore(ABC):
    @abstractmethod
    async def create(
        self,
        user_id: UUID,
        login: str,
        password_hash: str,
        role: Role,
        created_at: datetime,
    ) -> User:
        """Create a user or raise ``LoginTakenError`` for a case-insensitive clash."""

    @abstractmethod
    async def get_by_login(self, login: str) -> UserWithPassword | None:
        """Find a user by login without regard to case."""

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> User | None:
        """Return the current state of a user."""


class RefreshSessionStore(ABC):
    @abstractmethod
    async def create(self, session: RefreshSession) -> None:
        """Persist a new active refresh session."""

    @abstractmethod
    async def get_by_token_hash(self, token_hash: bytes) -> RefreshSession | None:
        """Find a session, active or revoked, by its token hash."""

    @abstractmethod
    async def rotate(
        self,
        current_id: UUID,
        replacement: RefreshSession,
        now: datetime,
    ) -> bool:
        """Atomically revoke an active session and persist its replacement.

        Returns ``False`` without changes if the session is no longer active.
        """

    @abstractmethod
    async def revoke(self, session_id: UUID, now: datetime) -> None:
        """Revoke a session if it is still active."""

    @abstractmethod
    async def revoke_family(self, family_id: UUID, now: datetime) -> None:
        """Revoke every active session of a rotation family."""


class TokenBlacklist(ABC):
    @abstractmethod
    async def add(self, jti: str, expires_at: datetime) -> None:
        """Reject the access token until its own expiry."""

    @abstractmethod
    async def contains(self, jti: str) -> bool:
        """Return whether the access token was revoked."""

    @abstractmethod
    async def revoke_family(self, family_id: UUID, until: datetime) -> None:
        """Reject every access token of a session family until ``until``."""

    @abstractmethod
    async def family_revoked(self, family_id: UUID) -> bool:
        """Return whether the session family was revoked."""


class AttemptLimiter(ABC):
    """Fixed-window counters keyed by opaque strings built by the service."""

    @abstractmethod
    async def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        """Count one request; return seconds until the window ends if over ``limit``."""

    @abstractmethod
    async def blocked(self, key: str, limit: int) -> int | None:
        """Return seconds until the window ends if failures reached ``limit``."""

    @abstractmethod
    async def record_failure(self, key: str, window_seconds: int) -> None:
        """Count one failure; the window starts at the first failure."""

    @abstractmethod
    async def reset(self, key: str) -> None:
        """Forget the counter of ``key``."""
