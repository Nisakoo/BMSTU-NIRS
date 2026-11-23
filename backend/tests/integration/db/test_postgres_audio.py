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
    PostgresMessageAudioStore,
    PostgresUserStore,
    create_engine,
)
from smeshariki_ai.db.migrate import upgrade
from smeshariki_ai.speech import AudioArtifact, SpeechStatus

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")
CONFIG = DatabaseConfig(url=DATABASE_URL or "postgresql+asyncpg://unused")


async def migrate_fresh() -> None:
    migration_engine = create_engine(CONFIG)
    async with migration_engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await migration_engine.dispose()
    await asyncio.to_thread(upgrade, create_engine(CONFIG), "head")


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


async def answer(engine: AsyncEngine) -> tuple[UUID, int]:
    owner = await add_user(engine, "krosh")
    history = PostgresHistoryStore(engine)
    dialog_id = await history.create(owner)
    _, answer_id = await history.append(
        dialog_id,
        (
            Message(role=MessageRole.USER, content="q"),
            Message(role=MessageRole.ASSISTANT, content="Однажды…"),
        ),
    )
    return dialog_id, answer_id


async def test_audio_metadata_is_stored_per_voice_and_deleted_with_dialog(
    engine: AsyncEngine,
) -> None:
    dialog_id, answer_id = await answer(engine)
    store = PostgresMessageAudioStore(engine)

    pending = await store.start(
        answer_id, "aidar", text_hash="hash", voice_version="v1"
    )
    assert pending.status is SpeechStatus.PENDING

    ready = await store.complete(
        answer_id,
        "aidar",
        text_hash="hash",
        voice_version="v1",
        artifact=AudioArtifact(data=b"mp3", duration_ms=1500),
        object_key="aidar.mp3",
        size_bytes=3,
        etag="etag",
    )
    assert ready is not None and ready.has_audio
    assert await store.get(answer_id, "aidar") == ready
    assert await store.get(answer_id, "baya") is None
    assert await store.ready_voices([answer_id]) == {answer_id: frozenset({"aidar"})}

    regenerating = await store.start(
        answer_id, "aidar", text_hash="hash", voice_version="v1"
    )
    assert regenerating.status is SpeechStatus.PENDING
    assert regenerating.object_key == "aidar.mp3"

    await store.start(answer_id, "baya", text_hash="hash", voice_version="v1")
    await store.complete(
        answer_id,
        "baya",
        text_hash="hash",
        voice_version="v1",
        artifact=AudioArtifact(data=b"mp3", duration_ms=1000),
        object_key="baya.mp3",
        size_bytes=3,
        etag="etag2",
    )
    assert await store.ready_voices([answer_id]) == {
        answer_id: frozenset({"aidar", "baya"})
    }

    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM dialogs WHERE id = :id"), {"id": dialog_id}
        )
        remaining = await connection.scalar(text("SELECT count(*) FROM message_audio"))
    assert remaining == 0


async def test_fail_and_reset_pending_keep_old_objects(engine: AsyncEngine) -> None:
    _, answer_id = await answer(engine)
    store = PostgresMessageAudioStore(engine)
    await store.start(answer_id, "aidar", text_hash="t", voice_version="v")
    await store.complete(
        answer_id,
        "aidar",
        text_hash="t",
        voice_version="v",
        artifact=AudioArtifact(data=b"mp3", duration_ms=10),
        object_key="old.mp3",
        size_bytes=3,
        etag="etag",
    )
    await store.start(answer_id, "aidar", text_hash="t", voice_version="v")
    failed = await store.fail(
        answer_id,
        "aidar",
        text_hash="t",
        voice_version="v",
        error_code="synthesis_failed",
    )
    assert failed is not None
    assert failed.status is SpeechStatus.READY
    assert failed.object_key == "old.mp3"

    await store.start(answer_id, "eugene", text_hash="t", voice_version="v")
    assert await store.reset_pending() == 1
    eugene = await store.get(answer_id, "eugene")
    assert eugene is not None
    assert eugene.status is SpeechStatus.FAILED
    assert eugene.error_code == "interrupted"


async def test_legacy_audio_bytes_can_be_backfilled(engine: AsyncEngine) -> None:
    _, answer_id = await answer(engine)
    store = PostgresMessageAudioStore(engine)
    await store.start(answer_id, "eugene", text_hash="t", voice_version="v")
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE message_audio SET status='ready', audio_data=:data, "
                "mime_type='audio/mpeg', duration_ms=10 "
                "WHERE message_id=:message_id AND voice_id='eugene'"
            ),
            {"data": b"legacy", "message_id": answer_id},
        )

    legacy = await store.legacy_records()
    assert len(legacy) == 1
    await store.clear_legacy_audio(
        answer_id,
        "eugene",
        object_key="legacy.mp3",
        size_bytes=6,
        etag="etag",
    )
    assert await store.legacy_records() == ()
    record = await store.get(answer_id, "eugene")
    assert record is not None
    assert record.object_key == "legacy.mp3"
    assert record.audio_data is None
