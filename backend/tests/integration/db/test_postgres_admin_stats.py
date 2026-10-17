import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.admin import AdminStatsUnavailableError, FeedbackStats
from smeshariki_ai.agent import Message, MessageRole
from smeshariki_ai.auth import RefreshSession, Role
from smeshariki_ai.db import (
    DatabaseConfig,
    PostgresAdminStatsStore,
    PostgresHistoryStore,
    PostgresRefreshSessionStore,
    PostgresUserStore,
    create_engine,
)
from smeshariki_ai.db.migrate import upgrade

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
SINCE = NOW - timedelta(days=7)

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


async def add_user(
    engine: AsyncEngine, login: str, *, days_ago: float, role: Role = Role.USER
) -> UUID:
    user = await PostgresUserStore(engine).create(
        uuid4(), login, "$argon2id$hash", role, NOW - timedelta(days=days_ago)
    )
    return user.id


async def add_activity(engine: AsyncEngine, user_id: UUID, *, days_ago: float) -> None:
    created_at = NOW - timedelta(days=days_ago)
    await PostgresRefreshSessionStore(engine).create(
        RefreshSession(
            id=uuid4(),
            user_id=user_id,
            family_id=uuid4(),
            token_hash=uuid4().bytes * 2,
            created_at=created_at,
            expires_at=created_at + timedelta(days=30),
        )
    )


async def test_empty_database_has_no_users(engine: AsyncEngine) -> None:
    snapshot = await PostgresAdminStatsStore(engine).user_stats(SINCE, 5)

    assert (snapshot.users_total, snapshot.new_users, snapshot.active_users) == (
        0,
        0,
        0,
    )
    assert snapshot.recent_users == ()


async def test_counts_users_new_registrations_and_distinct_active_users(
    engine: AsyncEngine,
) -> None:
    krosh = await add_user(engine, "Krosh", days_ago=100)
    nyusha = await add_user(engine, "Nyusha", days_ago=3)
    await add_user(engine, "Pin", days_ago=50)
    sovunya = await add_user(engine, "Sovunya", days_ago=1, role=Role.ADMIN)
    # Two sessions of one user in the window count once; old activity does not.
    await add_activity(engine, krosh, days_ago=2)
    await add_activity(engine, krosh, days_ago=0.5)
    await add_activity(engine, nyusha, days_ago=20)
    await add_activity(engine, sovunya, days_ago=0.1)

    snapshot = await PostgresAdminStatsStore(engine).user_stats(SINCE, 5)

    assert snapshot.users_total == 4
    assert snapshot.new_users == 2
    assert snapshot.active_users == 2


async def test_recent_users_follow_latest_activity_or_registration(
    engine: AsyncEngine,
) -> None:
    krosh = await add_user(engine, "Krosh", days_ago=100)
    nyusha = await add_user(engine, "Nyusha", days_ago=3)
    await add_user(engine, "Pin", days_ago=50)
    sovunya = await add_user(engine, "Sovunya", days_ago=1, role=Role.ADMIN)
    await add_user(engine, "Losyash", days_ago=200)
    await add_user(engine, "Barash", days_ago=150)
    await add_activity(engine, krosh, days_ago=2)
    await add_activity(engine, krosh, days_ago=0.5)
    await add_activity(engine, nyusha, days_ago=20)
    await add_activity(engine, sovunya, days_ago=0.1)

    snapshot = await PostgresAdminStatsStore(engine).user_stats(SINCE, 5)

    assert [user.login for user in snapshot.recent_users] == [
        "Sovunya",
        "Krosh",
        "Nyusha",
        "Pin",
        "Barash",
    ]
    by_login = {user.login: user for user in snapshot.recent_users}
    assert by_login["Sovunya"].role is Role.ADMIN
    assert by_login["Krosh"].last_active_at == NOW - timedelta(days=0.5)
    assert by_login["Krosh"].registered_at == NOW - timedelta(days=100)
    assert by_login["Nyusha"].last_active_at == NOW - timedelta(days=20)
    assert by_login["Pin"].last_active_at is None


async def test_unreachable_database_is_unavailable() -> None:
    engine = create_engine(
        DatabaseConfig(url="postgresql+asyncpg://user:pass@127.0.0.1:1/none")
    )
    try:
        with pytest.raises(AdminStatsUnavailableError):
            await PostgresAdminStatsStore(engine).user_stats(SINCE, 5)
    finally:
        await engine.dispose()


async def add_answers(
    engine: AsyncEngine, user_id: UUID, ratings: list[int | None], *, days_ago: float
) -> None:
    store = PostgresHistoryStore(engine)
    dialog_id = await store.create(user_id)
    for rating in ratings:
        _, answer_id = await store.append(
            dialog_id,
            (
                Message(role=MessageRole.USER, content="q"),
                Message(role=MessageRole.ASSISTANT, content="a"),
            ),
        )
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE messages SET created_at = :at WHERE dialog_id = :id"),
                {"at": NOW - timedelta(days=days_ago), "id": dialog_id},
            )
        if rating is not None:
            await store.set_feedback(user_id, dialog_id, answer_id, rating)


async def test_feedback_counts_answers_and_ratings_in_the_window(
    engine: AsyncEngine,
) -> None:
    krosh = await add_user(engine, "Krosh", days_ago=100)
    nyusha = await add_user(engine, "Nyusha", days_ago=100)
    await add_answers(engine, krosh, [5, 5, None, 1], days_ago=1)
    await add_answers(engine, nyusha, [4, None], days_ago=3)
    # Answers older than the window are not counted, even when rated.
    await add_answers(engine, nyusha, [2, 3], days_ago=30)

    snapshot = await PostgresAdminStatsStore(engine).user_stats(SINCE, 5)

    assert snapshot.feedback == FeedbackStats(
        answers_total=6, rated_answers=4, counts=(1, 0, 0, 1, 2)
    )


async def test_feedback_is_zero_without_answers(engine: AsyncEngine) -> None:
    snapshot = await PostgresAdminStatsStore(engine).user_stats(SINCE, 5)

    assert snapshot.feedback == FeedbackStats(0, 0, (0, 0, 0, 0, 0))
