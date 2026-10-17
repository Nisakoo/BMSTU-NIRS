"""Deterministic in-process stores for tests and local wiring."""

import asyncio
import math
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from smeshariki_ai.auth.models import (
    LoginTakenError,
    RefreshSession,
    Role,
    User,
    UserWithPassword,
)
from smeshariki_ai.auth.stores import (
    AttemptLimiter,
    RefreshSessionStore,
    TokenBlacklist,
    UserStore,
)


class InMemoryUserStore(UserStore):
    def __init__(self) -> None:
        self._users: dict[UUID, UserWithPassword] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        user_id: UUID,
        login: str,
        password_hash: str,
        role: Role,
        created_at: datetime,
    ) -> User:
        async with self._lock:
            if self._find(login) is not None:
                raise LoginTakenError
            user = User(id=user_id, login=login, role=role)
            self._users[user_id] = UserWithPassword(user, password_hash)
            return user

    async def get_by_login(self, login: str) -> UserWithPassword | None:
        async with self._lock:
            return self._find(login)

    async def get_by_id(self, user_id: UUID) -> User | None:
        async with self._lock:
            record = self._users.get(user_id)
            return None if record is None else record.user

    def set_role(self, user_id: UUID, role: Role) -> None:
        record = self._users[user_id]
        self._users[user_id] = replace(record, user=replace(record.user, role=role))

    def _find(self, login: str) -> UserWithPassword | None:
        normalized = login.lower()
        for record in self._users.values():
            if record.user.login.lower() == normalized:
                return record
        return None


class InMemoryRefreshSessionStore(RefreshSessionStore):
    def __init__(self) -> None:
        self._sessions: dict[UUID, RefreshSession] = {}
        self._lock = asyncio.Lock()

    async def create(self, session: RefreshSession) -> None:
        async with self._lock:
            self._sessions[session.id] = session

    async def get_by_token_hash(self, token_hash: bytes) -> RefreshSession | None:
        async with self._lock:
            for session in self._sessions.values():
                if session.token_hash == token_hash:
                    return session
            return None

    async def rotate(
        self,
        current_id: UUID,
        replacement: RefreshSession,
        now: datetime,
    ) -> bool:
        async with self._lock:
            current = self._sessions.get(current_id)
            if current is None or current.revoked_at is not None:
                return False
            self._sessions[current_id] = replace(
                current, revoked_at=now, replaced_by=replacement.id
            )
            self._sessions[replacement.id] = replacement
            return True

    async def revoke(self, session_id: UUID, now: datetime) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is not None and session.revoked_at is None:
                self._sessions[session_id] = replace(session, revoked_at=now)

    async def revoke_family(self, family_id: UUID, now: datetime) -> None:
        async with self._lock:
            for session_id, session in self._sessions.items():
                if session.family_id == family_id and session.revoked_at is None:
                    self._sessions[session_id] = replace(session, revoked_at=now)


class InMemoryTokenBlacklist(TokenBlacklist):
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self.expirations: dict[str, datetime] = {}
        self.family_expirations: dict[UUID, datetime] = {}

    async def add(self, jti: str, expires_at: datetime) -> None:
        if expires_at > self._clock():
            self.expirations[jti] = expires_at

    async def contains(self, jti: str) -> bool:
        expires_at = self.expirations.get(jti)
        return expires_at is not None and expires_at > self._clock()

    async def revoke_family(self, family_id: UUID, until: datetime) -> None:
        if until > self._clock():
            self.family_expirations[family_id] = until

    async def family_revoked(self, family_id: UUID) -> bool:
        until = self.family_expirations.get(family_id)
        return until is not None and until > self._clock()


class InMemoryAttemptLimiter(AttemptLimiter):
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._counters: dict[str, tuple[int, datetime]] = {}

    async def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        count = self._increment(key, window_seconds)
        return self._retry_after(key) if count > limit else None

    async def blocked(self, key: str, limit: int) -> int | None:
        self._expire(key)
        counter = self._counters.get(key)
        if counter is None or counter[0] < limit:
            return None
        return self._retry_after(key)

    async def record_failure(self, key: str, window_seconds: int) -> None:
        self._increment(key, window_seconds)

    async def reset(self, key: str) -> None:
        self._counters.pop(key, None)

    def _increment(self, key: str, window_seconds: int) -> int:
        self._expire(key)
        count, ends_at = self._counters.get(
            key, (0, self._clock() + timedelta(seconds=window_seconds))
        )
        self._counters[key] = (count + 1, ends_at)
        return count + 1

    def _expire(self, key: str) -> None:
        counter = self._counters.get(key)
        if counter is not None and counter[1] <= self._clock():
            del self._counters[key]

    def _retry_after(self, key: str) -> int:
        remaining = (self._counters[key][1] - self._clock()).total_seconds()
        return max(1, math.ceil(remaining))
