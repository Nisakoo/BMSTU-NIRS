import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.auth import (
    AuthUnavailableError,
    LoginTakenError,
    RefreshSession,
    Role,
)
from smeshariki_ai.db import (
    DatabaseConfig,
    PostgresRefreshSessionStore,
    PostgresUserStore,
    create_engine,
)
from smeshariki_ai.db.migrate import upgrade

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    config = DatabaseConfig(url=DATABASE_URL or "postgresql+asyncpg://unused")
    migration_engine = create_engine(config)
    async with migration_engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await migration_engine.dispose()
    # Alembic's async env runs its own event loop.
    await asyncio.to_thread(upgrade, create_engine(config))
    value = create_engine(config)
    try:
        yield value
    finally:
        await value.dispose()


def make_session(user_id, *, family_id=None, token=b"t" * 32):  # type: ignore[no-untyped-def]
    return RefreshSession(
        id=uuid4(),
        user_id=user_id,
        family_id=family_id or uuid4(),
        token_hash=token,
        created_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )


async def test_user_store_round_trip_and_case_insensitive_uniqueness(
    engine: AsyncEngine,
) -> None:
    store = PostgresUserStore(engine)
    user = await store.create(uuid4(), "Krosh", "$argon2id$hash", Role.USER, NOW)

    found = await store.get_by_login("kROSH")

    assert found is not None
    assert found.user == user
    assert found.password_hash == "$argon2id$hash"
    assert await store.get_by_id(user.id) == user
    assert await store.get_by_id(uuid4()) is None
    assert await store.get_by_login("Nyusha") is None
    with pytest.raises(LoginTakenError):
        await store.create(uuid4(), "KROSH", "$argon2id$other", Role.USER, NOW)


async def test_schema_rejects_invalid_role_and_login(engine: AsyncEngine) -> None:
    store = PostgresUserStore(engine)

    with pytest.raises(AuthUnavailableError):
        await store.create(uuid4(), "Кrosh", "hash", Role.USER, NOW)
    async with engine.connect() as connection:
        with pytest.raises(Exception, match="users_role_valid"):
            await connection.execute(
                text(
                    "INSERT INTO users (id, login, password_hash, role) "
                    "VALUES (gen_random_uuid(), 'root', 'hash', 'root')"
                )
            )


async def test_refresh_store_rotation_revocation_and_cascade(
    engine: AsyncEngine,
) -> None:
    user = await PostgresUserStore(engine).create(
        uuid4(), "Krosh", "hash", Role.USER, NOW
    )
    store = PostgresRefreshSessionStore(engine)
    first = make_session(user.id, token=b"1" * 32)
    await store.create(first)
    second = make_session(user.id, family_id=first.family_id, token=b"2" * 32)
    third = make_session(user.id, family_id=first.family_id, token=b"3" * 32)

    assert await store.rotate(first.id, second, NOW) is True
    assert await store.rotate(first.id, third, NOW) is False
    assert await store.get_by_token_hash(b"3" * 32) is None
    rotated = await store.get_by_token_hash(b"1" * 32)
    assert rotated is not None
    assert rotated.revoked_at == NOW
    assert rotated.replaced_by == second.id

    await store.revoke_family(first.family_id, NOW + timedelta(seconds=1))
    revoked = await store.get_by_token_hash(b"2" * 32)
    assert revoked is not None and revoked.revoked_at == NOW + timedelta(seconds=1)

    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM users"))
    assert await store.get_by_token_hash(b"2" * 32) is None


async def test_unreachable_database_is_unavailable() -> None:
    engine = create_engine(
        DatabaseConfig(url="postgresql+asyncpg://user:pass@127.0.0.1:1/none")
    )
    try:
        with pytest.raises(AuthUnavailableError):
            await PostgresUserStore(engine).get_by_login("Krosh")
    finally:
        await engine.dispose()
