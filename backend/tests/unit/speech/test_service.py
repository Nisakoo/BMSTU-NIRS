import asyncio
from uuid import UUID

import pytest

from smeshariki_ai.agent import Message, MessageRole
from smeshariki_ai.dialogs import (
    DialogNotFoundError,
    InMemoryHistoryStore,
    MessageNotFoundError,
)
from smeshariki_ai.speech.config import SpeechConfig
from smeshariki_ai.speech.errors import (
    SpeechSynthesisError,
    SpeechTextTooLongError,
    SpeechVoiceError,
)
from smeshariki_ai.speech.fake import FakeAudioEncoder, FakeSpeechProvider
from smeshariki_ai.speech.memory import InMemoryMessageAudioStore
from smeshariki_ai.speech.memory_objects import InMemoryAudioObjectStore
from smeshariki_ai.speech.models import SpeechStatus
from smeshariki_ai.speech.service import NarratorSpeechService

OWNER = UUID(int=1)
STRANGER = UUID(int=2)


async def make_service(
    *,
    answer: str = "Однажды Крош пошёл гулять. Ёжик остался дома.",
    max_text_chars: int = 20_000,
    provider: FakeSpeechProvider | None = None,
) -> tuple[
    NarratorSpeechService,
    InMemoryHistoryStore,
    InMemoryMessageAudioStore,
    InMemoryAudioObjectStore,
    UUID,
    int,
    FakeSpeechProvider,
]:
    history = InMemoryHistoryStore()
    dialog_id = await history.create(OWNER)
    _, answer_id = await history.append(
        dialog_id,
        (
            Message(role=MessageRole.USER, content="q"),
            Message(role=MessageRole.ASSISTANT, content=answer),
        ),
    )
    audio = InMemoryMessageAudioStore()
    objects = InMemoryAudioObjectStore()
    speech_provider = provider or FakeSpeechProvider()
    service = NarratorSpeechService(
        history_store=history,
        audio_store=audio,
        object_store=objects,
        provider=speech_provider,
        encoder=FakeAudioEncoder(),
        config=SpeechConfig(voice="baya", max_text_chars=max_text_chars),
    )
    return service, history, audio, objects, dialog_id, answer_id, speech_provider


async def wait_for_task(
    service: NarratorSpeechService, message_id: int, voice: str = "baya"
) -> None:
    await service._tasks[(message_id, voice)]


@pytest.mark.asyncio
async def test_request_generates_mp3_in_ceph_and_stores_metadata() -> None:
    service, _, audio, objects, dialog_id, answer_id, provider = await make_service()

    pending = await service.request(OWNER, dialog_id, answer_id, "aidar")
    assert pending.status is SpeechStatus.PENDING
    await wait_for_task(service, answer_id, "aidar")

    payload = await service.get(OWNER, dialog_id, answer_id, "aidar")
    assert payload is not None
    assert payload.data == b"fake-mp3"
    assert payload.record.status is SpeechStatus.READY
    assert payload.record.voice_id == "aidar"
    assert payload.record.object_key is not None
    assert payload.record.object_key in objects.objects
    assert len(provider.calls) == 1

    record = await audio.get(answer_id, "aidar")
    assert record is not None
    assert record.has_audio is True


@pytest.mark.asyncio
async def test_each_post_regenerates_and_keeps_old_object_until_success() -> None:
    service, _, _, objects, dialog_id, answer_id, provider = await make_service()

    await service.request(OWNER, dialog_id, answer_id, "aidar")
    await wait_for_task(service, answer_id, "aidar")
    first = await service.get(OWNER, dialog_id, answer_id, "aidar")
    assert first is not None
    first_key = first.record.object_key

    await service.request(OWNER, dialog_id, answer_id, "aidar")
    await wait_for_task(service, answer_id, "aidar")
    second = await service.get(OWNER, dialog_id, answer_id, "aidar")

    assert second is not None
    assert second.record.object_key != first_key
    assert first_key in objects.deleted
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_failed_regeneration_keeps_the_old_audio() -> None:
    service, _, _, objects, dialog_id, answer_id, _ = await make_service()
    await service.request(OWNER, dialog_id, answer_id, "aidar")
    await wait_for_task(service, answer_id, "aidar")
    old = await service.get(OWNER, dialog_id, answer_id, "aidar")
    assert old is not None

    class FailingProvider(FakeSpeechProvider):
        async def synthesize(self, text: str, *, voice: str) -> bytes:
            raise SpeechSynthesisError("private details")

    service._provider = FailingProvider()
    await service.request(OWNER, dialog_id, answer_id, "aidar")
    await wait_for_task(service, answer_id, "aidar")

    current = await service.get(OWNER, dialog_id, answer_id, "aidar")
    assert current is not None
    assert current.record.status is SpeechStatus.READY
    assert current.record.object_key == old.record.object_key
    assert current.data == b"fake-mp3"


@pytest.mark.asyncio
async def test_request_rejects_foreign_user_and_unknown_voice() -> None:
    service, history, _, _, dialog_id, answer_id, _ = await make_service()
    question_id = (await history.transcript(OWNER, dialog_id)).messages[0].id

    with pytest.raises(DialogNotFoundError):
        await service.request(STRANGER, dialog_id, answer_id, "aidar")
    with pytest.raises(MessageNotFoundError):
        await service.request(OWNER, dialog_id, question_id, "aidar")
    with pytest.raises(SpeechVoiceError):
        await service.request(OWNER, dialog_id, answer_id, "shrek")


@pytest.mark.asyncio
async def test_request_rejects_text_above_the_configured_limit() -> None:
    service, _, _, _, dialog_id, answer_id, provider = await make_service(
        max_text_chars=10
    )

    with pytest.raises(SpeechTextTooLongError):
        await service.request(OWNER, dialog_id, answer_id, "aidar")

    assert provider.calls == []


@pytest.mark.asyncio
async def test_available_voices_returns_existing_objects() -> None:
    service, _, _, _, dialog_id, answer_id, _ = await make_service()
    await service.request(OWNER, dialog_id, answer_id, "aidar")
    await wait_for_task(service, answer_id, "aidar")

    assert await service.available_voices([answer_id]) == {
        answer_id: frozenset({"aidar"})
    }


@pytest.mark.asyncio
async def test_shutdown_cancels_a_running_generation() -> None:
    class SlowProvider(FakeSpeechProvider):
        async def synthesize(self, text: str, *, voice: str) -> bytes:
            await asyncio.sleep(30)
            return b"wav"

    service, _, _, _, dialog_id, answer_id, _ = await make_service(
        provider=SlowProvider()
    )

    await service.request(OWNER, dialog_id, answer_id, "aidar")
    await asyncio.sleep(0)
    await service.shutdown()

    record = await service._audio_store.get(answer_id, "aidar")
    assert record is not None
    assert record.status is SpeechStatus.PENDING


@pytest.mark.asyncio
async def test_startup_marks_old_pending_work_as_interrupted() -> None:
    service, _, audio, _, _, answer_id, _ = await make_service()
    await audio.start(answer_id, "aidar", text_hash="old", voice_version="old")

    await service.startup()

    record = await audio.get(answer_id, "aidar")
    assert record is not None
    assert record.status is SpeechStatus.FAILED
    assert record.error_code == "interrupted"
