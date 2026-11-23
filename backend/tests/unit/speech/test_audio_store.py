import asyncio

import pytest

from smeshariki_ai.speech.memory import InMemoryMessageAudioStore
from smeshariki_ai.speech.models import AudioArtifact, SpeechStatus


@pytest.fixture
def store() -> InMemoryMessageAudioStore:
    return InMemoryMessageAudioStore()


@pytest.mark.asyncio
async def test_start_creates_one_pending_record_per_voice(
    store: InMemoryMessageAudioStore,
) -> None:
    first = await store.start(1, "aidar", text_hash="text-1", voice_version="voice-1")
    second = await store.start(1, "aidar", text_hash="text-1", voice_version="voice-1")

    assert first.status is SpeechStatus.PENDING
    assert second == first
    assert await store.get(1, "aidar") == first
    assert await store.get(1, "baya") is None


@pytest.mark.asyncio
async def test_start_keeps_the_previous_object_for_a_new_generation(
    store: InMemoryMessageAudioStore,
) -> None:
    await store.start(1, "aidar", text_hash="text-1", voice_version="voice-1")
    ready = await store.complete(
        1,
        "aidar",
        text_hash="text-1",
        voice_version="voice-1",
        artifact=AudioArtifact(data=b"mp3", duration_ms=500),
        object_key="old.mp3",
        size_bytes=3,
        etag="etag",
    )
    assert ready is not None and ready.has_audio

    regenerating = await store.start(
        1, "aidar", text_hash="text-1", voice_version="voice-1"
    )

    assert regenerating.status is SpeechStatus.PENDING
    assert regenerating.object_key == "old.mp3"
    assert regenerating.mime_type == "audio/mpeg"


@pytest.mark.asyncio
async def test_complete_stores_object_metadata_and_clears_legacy_bytes(
    store: InMemoryMessageAudioStore,
) -> None:
    await store.start(1, "aidar", text_hash="text-1", voice_version="voice-1")

    ready = await store.complete(
        1,
        "aidar",
        text_hash="text-1",
        voice_version="voice-1",
        artifact=AudioArtifact(data=b"mp3", duration_ms=500),
        object_key="new.mp3",
        size_bytes=3,
        etag="etag",
    )

    assert ready is not None
    assert ready.status is SpeechStatus.READY
    assert ready.object_key == "new.mp3"
    assert ready.size_bytes == 3
    assert ready.etag == "etag"
    assert ready.audio_data is None


@pytest.mark.asyncio
async def test_fail_keeps_old_audio_ready_or_marks_new_one_failed(
    store: InMemoryMessageAudioStore,
) -> None:
    await store.start(1, "aidar", text_hash="t", voice_version="v")
    failed = await store.fail(
        1,
        "aidar",
        text_hash="t",
        voice_version="v",
        error_code="synthesis_failed",
    )
    assert failed is not None and failed.status is SpeechStatus.FAILED
    assert failed.error_code == "synthesis_failed"

    await store.start(2, "aidar", text_hash="t", voice_version="v")
    await store.complete(
        2,
        "aidar",
        text_hash="t",
        voice_version="v",
        artifact=AudioArtifact(data=b"mp3", duration_ms=10),
        object_key="old.mp3",
        size_bytes=3,
        etag="etag",
    )
    await store.start(2, "aidar", text_hash="t", voice_version="v")
    old_kept = await store.fail(
        2,
        "aidar",
        text_hash="t",
        voice_version="v",
        error_code="synthesis_failed",
    )
    assert old_kept is not None
    assert old_kept.status is SpeechStatus.READY
    assert old_kept.object_key == "old.mp3"


@pytest.mark.asyncio
async def test_reset_pending_restores_old_objects_and_fails_empty_rows(
    store: InMemoryMessageAudioStore,
) -> None:
    await store.start(1, "aidar", text_hash="t", voice_version="v")
    await store.start(2, "aidar", text_hash="t", voice_version="v")
    await store.complete(
        2,
        "aidar",
        text_hash="t",
        voice_version="v",
        artifact=AudioArtifact(data=b"mp3", duration_ms=10),
        object_key="old.mp3",
        size_bytes=3,
        etag="etag",
    )
    await store.start(2, "aidar", text_hash="t", voice_version="v")

    assert await store.reset_pending() == 2
    assert (await store.get(1, "aidar")).status is SpeechStatus.FAILED
    assert (await store.get(1, "aidar")).error_code == "interrupted"
    assert (await store.get(2, "aidar")).status is SpeechStatus.READY


@pytest.mark.asyncio
async def test_ready_voices_groups_objects_by_message(
    store: InMemoryMessageAudioStore,
) -> None:
    await store.start(1, "aidar", text_hash="t", voice_version="v")
    await store.complete(
        1,
        "aidar",
        text_hash="t",
        voice_version="v",
        artifact=AudioArtifact(data=b"mp3", duration_ms=10),
        object_key="aidar.mp3",
        size_bytes=3,
        etag="etag",
    )
    await store.start(1, "eugene", text_hash="t", voice_version="v")
    await store.complete(
        1,
        "eugene",
        text_hash="t",
        voice_version="v",
        artifact=AudioArtifact(data=b"mp3", duration_ms=10),
        object_key="eugene.mp3",
        size_bytes=3,
        etag="etag",
    )
    await store.start(2, "aidar", text_hash="t", voice_version="v")

    assert await store.ready_voices([1, 2]) == {1: frozenset({"aidar", "eugene"})}


@pytest.mark.asyncio
async def test_legacy_audio_can_be_moved_to_object_storage(
    store: InMemoryMessageAudioStore,
) -> None:
    record = await store.start(1, "eugene", text_hash="t", voice_version="v")
    store._records[(1, "eugene")] = record.__class__(
        message_id=1,
        voice_id="eugene",
        status=SpeechStatus.READY,
        text_hash="t",
        voice_version="v",
        mime_type="audio/mpeg",
        duration_ms=10,
        audio_data=b"legacy",
    )

    legacy = await store.legacy_records()
    assert len(legacy) == 1
    await store.clear_legacy_audio(
        1,
        "eugene",
        object_key="eugene.mp3",
        size_bytes=6,
        etag="etag",
    )
    assert await store.legacy_records() == ()
    assert (await store.get(1, "eugene")).object_key == "eugene.mp3"


@pytest.mark.asyncio
async def test_concurrent_starts_do_not_create_parallel_pending_requests(
    store: InMemoryMessageAudioStore,
) -> None:
    records = await asyncio.gather(
        *(
            store.start(1, "aidar", text_hash="text", voice_version="voice")
            for _ in range(5)
        )
    )

    assert len({record.status for record in records}) == 1
    assert len({record.text_hash for record in records}) == 1
