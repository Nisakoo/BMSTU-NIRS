import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
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
from smeshariki_ai.db.migrate import upgrade
from smeshariki_ai.dialogs import (
    DialogNotFoundError,
    DialogStoreUnavailableError,
    MessageNotFoundError,
)

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")


CONFIG = DatabaseConfig(url=DATABASE_URL or "postgresql+asyncpg://unused")


async def migrate_fresh(revision: str = "head") -> None:
    migration_engine = create_engine(CONFIG)
    async with migration_engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await migration_engine.dispose()
    # Alembic's async env runs its own event loop.
    await asyncio.to_thread(upgrade, create_engine(CONFIG), revision)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    await migrate_fresh()
    value = create_engine(CONFIG)
    try:
        yield value
    finally:
        await value.dispose()


async def add_user(engine: AsyncEngine, login: str) -> UUID:
    user = await PostgresUserStore(engine).create(
        uuid4(), login, "$argon2id$hash", Role.USER, NOW
    )
    return user.id


def pair(question: str, answer: str = "answer") -> tuple[Message, Message]:
    return (
        Message(role=MessageRole.USER, content=question),
        Message(role=MessageRole.ASSISTANT, content=answer),
    )


async def test_history_is_ordered_titled_and_owned(engine: AsyncEngine) -> None:
    owner = await add_user(engine, "krosh")
    stranger = await add_user(engine, "nyusha")
    store = PostgresHistoryStore(engine)
    dialog_id = await store.create(owner)

    assert dialog_id.version == 4
    assert await store.get(owner, dialog_id) == ()
    assert (await store.transcript(owner, dialog_id)).title is None

    await store.append(dialog_id, pair("  Крош   строит\nракету ", "Однажды…"))
    await store.append(dialog_id, pair("Дальше", "Потом…"))

    assert await store.get(owner, dialog_id) == (
        *pair("  Крош   строит\nракету ", "Однажды…"),
        *pair("Дальше", "Потом…"),
    )
    transcript = await store.transcript(owner, dialog_id)
    assert transcript.title == "Крош строит ракету"
    assert [item.role for item in transcript.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert all(item.created_at.tzinfo is not None for item in transcript.messages)
    with pytest.raises(DialogNotFoundError):
        await store.get(stranger, dialog_id)
    with pytest.raises(DialogNotFoundError):
        await store.transcript(stranger, dialog_id)
    with pytest.raises(DialogNotFoundError):
        await store.append(uuid4(), pair("lost"))


async def test_list_filters_orders_and_limits(engine: AsyncEngine) -> None:
    owner = await add_user(engine, "krosh")
    stranger = await add_user(engine, "nyusha")
    store = PostgresHistoryStore(engine)
    older = await store.create(owner)
    newer = await store.create(owner)
    await store.create(owner)
    await store.append(await store.create(stranger), pair("чужая"))
    await store.append(older, pair("first"))
    await store.append(newer, pair("second"))
    first_update = (await store.list_dialogs(owner, limit=50))[1].updated_at
    await store.append(older, pair("third"))

    dialogs = await store.list_dialogs(owner, limit=50)

    assert [item.dialog_id for item in dialogs] == [older, newer]
    assert [item.title for item in dialogs] == ["first", "second"]
    assert dialogs[0].updated_at > first_update
    assert len(await store.list_dialogs(owner, limit=1)) == 1


async def test_list_returns_at_most_fifty(engine: AsyncEngine) -> None:
    owner = await add_user(engine, "krosh")
    store = PostgresHistoryStore(engine)
    for index in range(51):
        await store.append(await store.create(owner), pair(f"story {index}"))

    assert len(await store.list_dialogs(owner, limit=50)) == 50


async def test_deleting_a_user_removes_dialogs_and_messages(
    engine: AsyncEngine,
) -> None:
    owner = await add_user(engine, "krosh")
    store = PostgresHistoryStore(engine)
    await store.append(await store.create(owner), pair("story"))

    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM users WHERE id = :id"), {"id": owner}
        )
        dialogs = await connection.scalar(text("SELECT count(*) FROM dialogs"))
        messages = await connection.scalar(text("SELECT count(*) FROM messages"))

    assert (dialogs, messages) == (0, 0)


async def test_concurrent_appends_keep_unique_positions(engine: AsyncEngine) -> None:
    owner = await add_user(engine, "krosh")
    store = PostgresHistoryStore(engine)
    dialog_id = await store.create(owner)

    await asyncio.gather(*(store.append(dialog_id, pair(f"q{i}")) for i in range(5)))

    assert len(await store.get(owner, dialog_id)) == 10


async def test_unreachable_database_is_unavailable() -> None:
    engine = create_engine(
        DatabaseConfig(url="postgresql+asyncpg://user:pass@127.0.0.1:1/none")
    )
    try:
        with pytest.raises(DialogStoreUnavailableError):
            await PostgresHistoryStore(engine).list_dialogs(uuid4(), limit=50)
    finally:
        await engine.dispose()


async def test_append_returns_ids_and_feedback_is_stored(engine: AsyncEngine) -> None:
    owner = await add_user(engine, "krosh")
    store = PostgresHistoryStore(engine)
    dialog_id = await store.create(owner)

    ids = await store.append(dialog_id, pair("q1"))
    more = await store.append(dialog_id, pair("q2"))
    transcript = await store.transcript(owner, dialog_id)
    assert [item.id for item in transcript.messages] == [*ids, *more]
    assert [item.feedback for item in transcript.messages] == [None] * 4

    await store.set_feedback(owner, dialog_id, ids[1], 5)
    await store.set_feedback(owner, dialog_id, more[1], 4)
    await store.set_feedback(owner, dialog_id, more[1], 2)
    await store.clear_feedback(owner, dialog_id, ids[1])
    await store.clear_feedback(owner, dialog_id, ids[1])

    transcript = await store.transcript(owner, dialog_id)
    assert [item.feedback for item in transcript.messages] == [
        None,
        None,
        None,
        2,
    ]


async def test_feedback_targets_only_own_assistant_answers(
    engine: AsyncEngine,
) -> None:
    owner = await add_user(engine, "krosh")
    stranger = await add_user(engine, "nyusha")
    store = PostgresHistoryStore(engine)
    dialog_id = await store.create(owner)
    other_id = await store.create(owner)
    question_id, answer_id = await store.append(dialog_id, pair("q"))
    _, other_answer = await store.append(other_id, pair("o"))

    for user, target, message_id in (
        (owner, dialog_id, question_id),
        (stranger, dialog_id, answer_id),
        (owner, dialog_id, other_answer),
        (owner, dialog_id, 10_000_000),
        (owner, uuid4(), answer_id),
    ):
        with pytest.raises(MessageNotFoundError):
            await store.set_feedback(user, target, message_id, 5)
        with pytest.raises(MessageNotFoundError):
            await store.clear_feedback(user, target, message_id)

    async with engine.connect() as connection:
        assert (
            await connection.scalar(text("SELECT count(*) FROM message_feedback")) == 0
        )


async def test_deleting_a_user_removes_feedback(engine: AsyncEngine) -> None:
    owner = await add_user(engine, "krosh")
    store = PostgresHistoryStore(engine)
    dialog_id = await store.create(owner)
    _, answer_id = await store.append(dialog_id, pair("q"))
    await store.set_feedback(owner, dialog_id, answer_id, 5)

    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM users WHERE id = :id"), {"id": owner}
        )
        remaining = await connection.scalar(
            text("SELECT count(*) FROM message_feedback")
        )

    assert remaining == 0


@pytest.mark.parametrize("score", [0, 6])
async def test_score_outside_one_to_five_is_rejected(
    engine: AsyncEngine, score: int
) -> None:
    owner = await add_user(engine, "krosh")
    store = PostgresHistoryStore(engine)
    dialog_id = await store.create(owner)
    _, answer_id = await store.append(dialog_id, pair("q"))

    with pytest.raises(DialogStoreUnavailableError):
        await store.set_feedback(owner, dialog_id, answer_id, score)


async def test_migration_turns_likes_into_scores() -> None:
    await migrate_fresh("0003")
    engine = create_engine(CONFIG)
    try:
        owner = await add_user(engine, "krosh")
        store = PostgresHistoryStore(engine)
        dialog_id = await store.create(owner)
        _, liked = await store.append(dialog_id, pair("q1"))
        _, disliked = await store.append(dialog_id, pair("q2"))
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO message_feedback (message_id, value) "
                    "VALUES (:liked, 'like'), (:disliked, 'dislike')"
                ),
                {"liked": liked, "disliked": disliked},
            )
    finally:
        await engine.dispose()

    await asyncio.to_thread(upgrade, create_engine(CONFIG))

    engine = create_engine(CONFIG)
    try:
        transcript = await PostgresHistoryStore(engine).transcript(owner, dialog_id)
    finally:
        await engine.dispose()
    assert [item.feedback for item in transcript.messages] == [None, 5, None, 1]
