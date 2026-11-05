import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.admin import (
    AdminStatsUnavailableError,
    FeedbackStats,
    ReportNotFoundError,
    ReportStatus,
)
from smeshariki_ai.agent import Message, MessageRole
from smeshariki_ai.auth import RefreshSession, Role
from smeshariki_ai.db import (
    DatabaseConfig,
    PostgresAdminStatsStore,
    PostgresHistoryStore,
    PostgresRefreshSessionStore,
    PostgresReportStore,
    PostgresUserStore,
    create_engine,
)
from smeshariki_ai.db.migrate import upgrade
from smeshariki_ai.dialogs import ReportReason

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


async def add_reports(engine: AsyncEngine, user_id: UUID, count: int) -> list[int]:
    store = PostgresHistoryStore(engine)
    dialog_id = await store.create(user_id)
    ids = []
    for number in range(count):
        _, answer_id = await store.append(
            dialog_id,
            (
                Message(role=MessageRole.USER, content=f"вопрос {number}"),
                Message(role=MessageRole.ASSISTANT, content=f"ответ {number}"),
            ),
        )
        ids.append(
            await store.report(
                user_id, dialog_id, answer_id, ReportReason.RUDE, f"к {number}"
            )
        )
    return ids


async def test_reports_are_listed_newest_first_by_status(engine: AsyncEngine) -> None:
    krosh = await add_user(engine, "Krosh", days_ago=10)
    admin = await add_user(engine, "Sovunya", days_ago=10, role=Role.ADMIN)
    first, second, third = await add_reports(engine, krosh, 3)
    store = PostgresReportStore(engine)

    await store.set_status(second, ReportStatus.RESOLVED, admin)
    await store.set_status(third, ReportStatus.DISMISSED, admin)

    new = await store.list_reports(ReportStatus.NEW, 50)
    every = await store.list_reports(None, 50)
    assert [item.id for item in new] == [first]
    assert [item.id for item in every] == [third, second, first]
    assert [item.id for item in await store.list_reports(None, 2)] == [third, second]
    report = new[0]
    assert (report.reason, report.comment) == (ReportReason.RUDE, "к 0")
    assert (report.request_text, report.answer_text) == ("вопрос 0", "ответ 0")
    assert (report.resolved_at, report.dialog_deleted) == (None, False)
    resolved = every[1]
    assert resolved.status is ReportStatus.RESOLVED
    assert resolved.resolved_at is not None
    snapshot = await PostgresAdminStatsStore(engine).user_stats(SINCE, 5)
    assert snapshot.reports_new == 1


async def test_reopened_report_forgets_who_closed_it(engine: AsyncEngine) -> None:
    krosh = await add_user(engine, "Krosh", days_ago=10)
    admin = await add_user(engine, "Sovunya", days_ago=10, role=Role.ADMIN)
    [report_id] = await add_reports(engine, krosh, 1)
    store = PostgresReportStore(engine)

    await store.set_status(report_id, ReportStatus.RESOLVED, admin)
    await store.set_status(report_id, ReportStatus.NEW, admin)

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text("SELECT status, resolved_at, resolved_by FROM message_reports")
            )
        ).one()
    assert tuple(row) == ("new", None, None)
    with pytest.raises(ReportNotFoundError):
        await store.set_status(report_id + 1, ReportStatus.RESOLVED, admin)


async def test_report_of_a_deleted_dialog_is_marked(engine: AsyncEngine) -> None:
    krosh = await add_user(engine, "Krosh", days_ago=10)
    history = PostgresHistoryStore(engine)
    await add_reports(engine, krosh, 1)
    [summary] = await history.list_dialogs(krosh, limit=5)

    await history.delete(krosh, summary.dialog_id)

    [report] = await PostgresReportStore(engine).list_reports(None, 50)
    assert report.dialog_deleted is True
    assert report.answer_text == "ответ 0"


async def add_story(
    engine: AsyncEngine, user_id: UUID, *, days_ago: float, pairs: int = 1
) -> UUID:
    store = PostgresHistoryStore(engine)
    dialog_id = await store.create(user_id)
    for number in range(pairs):
        await store.append(
            dialog_id,
            (
                Message(role=MessageRole.USER, content=f"q{number}"),
                Message(role=MessageRole.ASSISTANT, content=f"a{number}"),
            ),
        )
    at = NOW - timedelta(days=days_ago)
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE dialogs SET created_at = :at WHERE id = :id"),
            {"at": at, "id": dialog_id},
        )
        await connection.execute(
            text("UPDATE messages SET created_at = :at WHERE dialog_id = :id"),
            {"at": at, "id": dialog_id},
        )
    return dialog_id


async def test_stories_messages_and_activity_count_only_dialogs_with_messages(
    engine: AsyncEngine,
) -> None:
    krosh = await add_user(engine, "Krosh", days_ago=100)
    nyusha = await add_user(engine, "Nyusha", days_ago=100)
    await add_story(engine, krosh, days_ago=0.5)
    await add_story(engine, krosh, days_ago=1.5, pairs=2)
    await add_story(engine, krosh, days_ago=6.5)
    await add_story(engine, nyusha, days_ago=3.2)
    # Outside the window: counted for the user, not for the period.
    await add_story(engine, nyusha, days_ago=10)
    # Opening the chat creates an empty dialog; it is not a story.
    for _ in range(3):
        await PostgresHistoryStore(engine).create(krosh)

    snapshot = await PostgresAdminStatsStore(engine).user_stats(
        SINCE, 5, bucket=timedelta(days=1), buckets=7
    )

    assert snapshot.dialogs == 4
    assert snapshot.messages == 10
    assert snapshot.activity == (1, 0, 0, 1, 0, 1, 1)
    assert sum(snapshot.activity) == snapshot.dialogs
    by_login = {user.login: user.dialogs for user in snapshot.recent_users}
    assert by_login == {"Krosh": 3, "Nyusha": 2}


async def test_activity_covers_longer_buckets_and_an_empty_period(
    engine: AsyncEngine,
) -> None:
    store = PostgresAdminStatsStore(engine)
    since = NOW - timedelta(days=30)

    empty = await store.user_stats(since, 5, bucket=timedelta(days=3), buckets=10)
    krosh = await add_user(engine, "Krosh", days_ago=100)
    await add_story(engine, krosh, days_ago=29)
    await add_story(engine, krosh, days_ago=0.1)
    filled = await store.user_stats(since, 5, bucket=timedelta(days=3), buckets=10)

    assert (empty.dialogs, empty.messages, empty.activity) == (0, 0, (0,) * 10)
    assert filled.activity == (1, 0, 0, 0, 0, 0, 0, 0, 0, 1)
