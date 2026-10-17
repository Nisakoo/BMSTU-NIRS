import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.agent import Message, MessageRole
from smeshariki_ai.auth import Role
from smeshariki_ai.db import (
    DatabaseConfig,
    PostgresHistoryStore,
    PostgresUserStore,
    create_engine,
)
from smeshariki_ai.db.migrate import downgrade, upgrade
from smeshariki_ai.dialogs import (
    DialogCursor,
    DialogNotFoundError,
    HistoryUnavailableError,
)

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
PAIR = (
    Message(role=MessageRole.USER, content="question"),
    Message(role=MessageRole.ASSISTANT, content="answer"),
)

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")


def make_config() -> DatabaseConfig:
    return DatabaseConfig(url=DATABASE_URL or "postgresql+asyncpg://unused")


async def reset_schema() -> None:
    engine = create_engine(make_config())
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    await reset_schema()
    # Alembic's async env runs its own event loop.
    await asyncio.to_thread(upgrade, create_engine(make_config()))
    value = create_engine(make_config())
    try:
        yield value
    finally:
        await value.dispose()


async def make_user(engine: AsyncEngine, login: str = "Krosh") -> UUID:
    user = await PostgresUserStore(engine).create(
        uuid4(), login, "hash", Role.USER, NOW
    )
    return user.id


async def table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
    return {row.tablename for row in rows}


async def count(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as connection:
        result = await connection.execute(text(f"SELECT count(*) FROM {table}"))
        return result.scalar_one()


async def test_migration_0002_upgrades_downgrades_and_upgrades_again(
    engine: AsyncEngine,
) -> None:
    assert {"dialogs", "messages"} <= await table_names(engine)

    await asyncio.to_thread(downgrade, create_engine(make_config()), "0001")
    names = await table_names(engine)
    assert {"dialogs", "messages"}.isdisjoint(names)
    assert {"users", "refresh_sessions"} <= names

    await asyncio.to_thread(upgrade, create_engine(make_config()))
    assert {"dialogs", "messages"} <= await table_names(engine)


async def test_create_is_readable_through_a_new_engine(engine: AsyncEngine) -> None:
    owner_id = await make_user(engine)
    dialog_id = uuid4()
    await PostgresHistoryStore(engine).create(dialog_id, owner_id, "Title", PAIR, NOW)

    restarted = create_engine(make_config())
    try:
        store = PostgresHistoryStore(restarted)
        assert await store.owner(dialog_id) == owner_id
        assert await store.get(dialog_id) == PAIR
        transcript = await store.read(dialog_id)
        assert transcript.title == "Title"
        assert [(m.role, m.content, m.created_at) for m in transcript.messages] == [
            (MessageRole.USER, "question", NOW),
            (MessageRole.ASSISTANT, "answer", NOW),
        ]
        (summary,) = await store.list(owner_id, 10, None)
        assert (summary.dialog_id, summary.title) == (dialog_id, "Title")
        assert (summary.created_at, summary.updated_at) == (NOW, NOW)
    finally:
        await restarted.dispose()


async def test_append_numbers_positions_and_updates_only_updated_at(
    engine: AsyncEngine,
) -> None:
    owner_id = await make_user(engine)
    store = PostgresHistoryStore(engine)
    dialog_id = uuid4()
    await store.create(dialog_id, owner_id, "Title", PAIR, NOW)
    later = NOW + timedelta(minutes=1)

    await store.append(dialog_id, PAIR, later)

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text("SELECT position FROM messages ORDER BY position")
            )
        ).all()
    assert [row.position for row in rows] == [0, 1, 2, 3]
    (summary,) = await store.list(owner_id, 10, None)
    assert (summary.title, summary.created_at, summary.updated_at) == (
        "Title",
        NOW,
        later,
    )
    assert len(await store.get(dialog_id)) == 4


async def test_concurrent_appends_get_distinct_consecutive_positions(
    engine: AsyncEngine,
) -> None:
    owner_id = await make_user(engine)
    store = PostgresHistoryStore(engine)
    dialog_id = uuid4()
    await store.create(dialog_id, owner_id, None, PAIR, NOW)

    await asyncio.gather(
        *(store.append(dialog_id, PAIR, NOW + timedelta(seconds=n)) for n in range(5))
    )

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text("SELECT position FROM messages ORDER BY position")
            )
        ).all()
    assert [row.position for row in rows] == list(range(12))


async def test_failed_create_leaves_no_dialog_or_messages(engine: AsyncEngine) -> None:
    owner_id = await make_user(engine)
    store = PostgresHistoryStore(engine)
    invalid = (PAIR[0], Message(role=MessageRole.SYSTEM, content="not allowed"))

    with pytest.raises(HistoryUnavailableError) as caught:
        await store.create(uuid4(), owner_id, "Title", invalid, NOW)

    assert "not allowed" not in str(caught.value)
    assert await count(engine, "dialogs") == 0
    assert await count(engine, "messages") == 0


async def test_failed_append_changes_nothing(engine: AsyncEngine) -> None:
    owner_id = await make_user(engine)
    store = PostgresHistoryStore(engine)
    dialog_id = uuid4()
    await store.create(dialog_id, owner_id, "Title", PAIR, NOW)
    invalid = (PAIR[0], Message(role=MessageRole.TOOL, content="not allowed"))

    with pytest.raises(HistoryUnavailableError):
        await store.append(dialog_id, invalid, NOW + timedelta(minutes=1))

    assert await count(engine, "messages") == 2
    (summary,) = await store.list(owner_id, 10, None)
    assert summary.updated_at == NOW


async def test_unknown_dialog_raises_not_found(engine: AsyncEngine) -> None:
    store = PostgresHistoryStore(engine)
    missing = uuid4()

    for operation in (
        store.owner(missing),
        store.get(missing),
        store.read(missing),
        store.append(missing, PAIR, NOW),
        store.delete(missing),
    ):
        with pytest.raises(DialogNotFoundError) as caught:
            await operation
        assert caught.value.dialog_id == missing


async def test_list_pages_through_equal_updated_at_without_gaps(
    engine: AsyncEngine,
) -> None:
    owner_id = await make_user(engine)
    other_id = await make_user(engine, "Losyash")
    store = PostgresHistoryStore(engine)
    for index in range(7):
        # Pairs share the same updated_at, so the id breaks the tie.
        await store.create(
            uuid4(), owner_id, str(index), PAIR, NOW + timedelta(minutes=index // 2)
        )
    await store.create(uuid4(), other_id, "foreign", PAIR, NOW)

    seen: list[UUID] = []
    after: DialogCursor | None = None
    while page := await store.list(owner_id, 3, after):
        seen.extend(item.dialog_id for item in page)
        after = DialogCursor(
            updated_at=page[-1].updated_at, dialog_id=page[-1].dialog_id
        )

    full = await store.list(owner_id, 50, None)
    assert len(seen) == len(set(seen)) == 7
    assert seen == [item.dialog_id for item in full]
    assert [item.updated_at for item in full] == sorted(
        (item.updated_at for item in full), reverse=True
    )
    assert all(item.title != "foreign" for item in full)


async def test_delete_and_user_removal_cascade_to_messages(engine: AsyncEngine) -> None:
    owner_id = await make_user(engine)
    store = PostgresHistoryStore(engine)
    first, second = uuid4(), uuid4()
    await store.create(first, owner_id, "one", PAIR, NOW)
    await store.create(second, owner_id, "two", PAIR, NOW)

    await store.delete(first)

    assert await count(engine, "dialogs") == 1
    assert await count(engine, "messages") == 2
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM users"))
    assert await count(engine, "dialogs") == 0
    assert await count(engine, "messages") == 0


async def test_unreachable_database_is_unavailable() -> None:
    engine = create_engine(
        DatabaseConfig(url="postgresql+asyncpg://user:pass@127.0.0.1:1/none")
    )
    store = PostgresHistoryStore(engine)
    try:
        for operation in (
            store.owner(uuid4()),
            store.list(uuid4(), 10, None),
            store.create(uuid4(), uuid4(), None, PAIR, NOW),
        ):
            with pytest.raises(HistoryUnavailableError):
                await operation
    finally:
        await engine.dispose()
