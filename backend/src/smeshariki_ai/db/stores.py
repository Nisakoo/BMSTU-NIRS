from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID

from asyncpg import PostgresError
from sqlalchemy import Row, func, insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.auth import (
    AuthUnavailableError,
    LoginTakenError,
    RefreshSession,
    RefreshSessionStore,
    Role,
    User,
    UserStore,
    UserWithPassword,
)
from smeshariki_ai.db.tables import refresh_sessions, users

_LOGIN_UNIQUE_INDEX = "users_login_lower_key"


@contextmanager
def _unavailable_on_failure() -> Iterator[None]:
    try:
        yield
    except (SQLAlchemyError, PostgresError, OSError, TimeoutError) as error:
        raise AuthUnavailableError from error


class PostgresUserStore(UserStore):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(
        self,
        user_id: UUID,
        login: str,
        password_hash: str,
        role: Role,
        created_at: datetime,
    ) -> User:
        statement = insert(users).values(
            id=user_id,
            login=login,
            password_hash=password_hash,
            role=role.value,
            created_at=created_at,
            updated_at=created_at,
        )
        with _unavailable_on_failure():
            try:
                async with self._engine.begin() as connection:
                    await connection.execute(statement)
            except IntegrityError as error:
                if _LOGIN_UNIQUE_INDEX in str(error.orig):
                    raise LoginTakenError from error
                raise
        return User(id=user_id, login=login, role=role)

    async def get_by_login(self, login: str) -> UserWithPassword | None:
        statement = select(users).where(func.lower(users.c.login) == login.lower())
        with _unavailable_on_failure():
            async with self._engine.connect() as connection:
                row = (await connection.execute(statement)).first()
        if row is None:
            return None
        return UserWithPassword(_user(row), row.password_hash)

    async def get_by_id(self, user_id: UUID) -> User | None:
        statement = select(users).where(users.c.id == user_id)
        with _unavailable_on_failure():
            async with self._engine.connect() as connection:
                row = (await connection.execute(statement)).first()
        return None if row is None else _user(row)


class PostgresRefreshSessionStore(RefreshSessionStore):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(self, session: RefreshSession) -> None:
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                await connection.execute(_insert_session(session))

    async def get_by_token_hash(self, token_hash: bytes) -> RefreshSession | None:
        statement = select(refresh_sessions).where(
            refresh_sessions.c.token_hash == token_hash
        )
        with _unavailable_on_failure():
            async with self._engine.connect() as connection:
                row = (await connection.execute(statement)).first()
        return None if row is None else _session(row)

    async def rotate(
        self,
        current_id: UUID,
        replacement: RefreshSession,
        now: datetime,
    ) -> bool:
        revoke_current = (
            update(refresh_sessions)
            .where(
                refresh_sessions.c.id == current_id,
                refresh_sessions.c.revoked_at.is_(None),
            )
            .values(revoked_at=now, replaced_by=replacement.id)
        )
        with _unavailable_on_failure():
            async with self._engine.connect() as connection:
                async with connection.begin() as transaction:
                    # The replacement must exist before it can be referenced.
                    await connection.execute(_insert_session(replacement))
                    result = await connection.execute(revoke_current)
                    if result.rowcount != 1:
                        await transaction.rollback()
                        return False
        return True

    async def revoke(self, session_id: UUID, now: datetime) -> None:
        statement = (
            update(refresh_sessions)
            .where(
                refresh_sessions.c.id == session_id,
                refresh_sessions.c.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                await connection.execute(statement)

    async def revoke_family(self, family_id: UUID, now: datetime) -> None:
        statement = (
            update(refresh_sessions)
            .where(
                refresh_sessions.c.family_id == family_id,
                refresh_sessions.c.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                await connection.execute(statement)


def _insert_session(session: RefreshSession):  # type: ignore[no-untyped-def]
    return insert(refresh_sessions).values(
        id=session.id,
        user_id=session.user_id,
        family_id=session.family_id,
        token_hash=session.token_hash,
        created_at=session.created_at,
        expires_at=session.expires_at,
        revoked_at=session.revoked_at,
        replaced_by=session.replaced_by,
    )


def _user(row: Row) -> User:  # type: ignore[type-arg]
    return User(id=row.id, login=row.login, role=Role(row.role))


def _session(row: Row) -> RefreshSession:  # type: ignore[type-arg]
    return RefreshSession(
        id=row.id,
        user_id=row.user_id,
        family_id=row.family_id,
        token_hash=bytes(row.token_hash),
        created_at=row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        replaced_by=row.replaced_by,
    )
