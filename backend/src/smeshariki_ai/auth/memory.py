"""Deterministic in-process stores for tests and local wiring."""

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from smeshariki_ai.auth.models import (
    LoginTakenError,
    RefreshSession,
    Role,
    User,
    UserWithPassword,
)
from smeshariki_ai.auth.stores import RefreshSessionStore, TokenBlacklist, UserStore


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

    async def add(self, jti: str, expires_at: datetime) -> None:
        if expires_at > self._clock():
            self.expirations[jti] = expires_at

    async def contains(self, jti: str) -> bool:
        expires_at = self.expirations.get(jti)
        return expires_at is not None and expires_at > self._clock()
