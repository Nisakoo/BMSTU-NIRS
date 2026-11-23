from collections.abc import AsyncIterator, Sequence
from uuid import UUID

import httpx
import pytest
from api_auth_support import (
    AUTH_COOKIES,
    OTHER_COOKIES,
    TEST_USER,
    static_auth_service,
)

from smeshariki_ai.agent import (
    AgentResponse,
    AgentStreamEvent,
    Message,
    MessageRole,
    UserRequest,
)
from smeshariki_ai.api import create_app
from smeshariki_ai.application import AgentService, InMemoryDialogEventBroker
from smeshariki_ai.dialogs import InMemoryHistoryStore
from smeshariki_ai.speech.config import SpeechConfig
from smeshariki_ai.speech.fake import FakeAudioEncoder, FakeSpeechProvider
from smeshariki_ai.speech.memory import InMemoryMessageAudioStore
from smeshariki_ai.speech.memory_objects import InMemoryAudioObjectStore
from smeshariki_ai.speech.service import NarratorSpeechService


class EchoAgent:
    async def run(
        self,
        history: Sequence[Message],
        request: UserRequest,
    ) -> AsyncIterator[AgentStreamEvent]:
        yield AgentResponse(content=f"ответ: {request.content}")


async def make_client(
    *,
    max_text_chars: int = 20_000,
    cookies: dict[str, str] | None = None,
) -> tuple[
    httpx.AsyncClient,
    UUID,
    int,
    NarratorSpeechService,
    FakeSpeechProvider,
    InMemoryAudioObjectStore,
]:
    history = InMemoryHistoryStore()
    dialog_id = await history.create(TEST_USER.id)
    _question_id, answer_id = await history.append(
        dialog_id,
        (
            Message(role=MessageRole.USER, content="q"),
            Message(
                role=MessageRole.ASSISTANT, content="Однажды Крош гулял. Ёжик спал."
            ),
        ),
    )
    provider = FakeSpeechProvider()
    objects = InMemoryAudioObjectStore()
    speech = NarratorSpeechService(
        history_store=history,
        audio_store=InMemoryMessageAudioStore(),
        object_store=objects,
        provider=provider,
        encoder=FakeAudioEncoder(),
        config=SpeechConfig(max_text_chars=max_text_chars),
    )
    service = AgentService(EchoAgent(), history, InMemoryDialogEventBroker())
    app = create_app(
        service,
        auth_service=static_auth_service(),
        speech_service=speech,
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=AUTH_COOKIES if cookies is None else cookies,
    )
    return client, dialog_id, answer_id, speech, provider, objects


async def wait_for_audio(
    speech: NarratorSpeechService, message_id: int, voice: str = "baya"
) -> None:
    await speech._tasks[(message_id, voice)]


@pytest.mark.asyncio
async def test_audio_is_generated_in_ceph_regenerated_and_downloaded() -> None:
    client, dialog_id, answer_id, speech, provider, objects = await make_client()

    async with client:
        started = await client.post(
            f"/api/v1/dialogs/{dialog_id}/messages/{answer_id}/audio",
            json={"voice": "aidar"},
        )
        assert started.status_code == 202
        assert started.json() == {"status": "pending"}
        await wait_for_audio(speech, answer_id, "aidar")

        audio = await client.get(
            f"/api/v1/dialogs/{dialog_id}/messages/{answer_id}/audio?voice=aidar"
        )
        assert audio.status_code == 200
        assert audio.content == b"fake-mp3"
        assert audio.headers["content-type"] == "audio/mpeg"
        assert audio.headers["content-disposition"] == (
            f'inline; filename="smeshariki-{answer_id}-aidar.mp3"'
        )
        first_key = next(iter(objects.objects))
        assert first_key in objects.objects

        again = await client.post(
            f"/api/v1/dialogs/{dialog_id}/messages/{answer_id}/audio",
            json={"voice": "aidar"},
        )
        assert again.status_code == 202
        await wait_for_audio(speech, answer_id, "aidar")
        assert first_key in objects.deleted
        assert len(provider.calls) == 2

        download = await client.get(
            f"/api/v1/dialogs/{dialog_id}/messages/{answer_id}/audio"
            "?voice=aidar&download=1"
        )
        assert download.status_code == 200
        assert download.headers["content-disposition"] == (
            f'attachment; filename="smeshariki-{answer_id}-aidar.mp3"'
        )

        messages = await client.get(f"/api/v1/dialogs/{dialog_id}/messages")
        assert messages.status_code == 200
        items = messages.json()["messages"]
        assert items[1]["audio_voices"] == ["aidar"]


@pytest.mark.asyncio
async def test_audio_without_voice_uses_default_and_rejects_unknown_voice() -> None:
    client, dialog_id, answer_id, speech, _, _ = await make_client()

    async with client:
        started = await client.post(
            f"/api/v1/dialogs/{dialog_id}/messages/{answer_id}/audio"
        )
        assert started.status_code == 202
        await wait_for_audio(speech, answer_id, "baya")
        unknown = await client.post(
            f"/api/v1/dialogs/{dialog_id}/messages/{answer_id}/audio",
            json={"voice": "shrek"},
        )

    assert unknown.status_code == 422
    assert unknown.json() == {"detail": "Unknown narrator voice."}


@pytest.mark.asyncio
async def test_audio_is_404_for_foreign_dialog_user_message_and_unknown_id() -> None:
    client, dialog_id, answer_id, _, provider, _ = await make_client()
    stranger_client, _, _, _, _, _ = await make_client(cookies=OTHER_COOKIES)
    async with stranger_client as stranger:
        response = await stranger.get(
            f"/api/v1/dialogs/{dialog_id}/messages/{answer_id}/audio"
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "Dialog not found."}
        posted = await stranger.post(
            f"/api/v1/dialogs/{dialog_id}/messages/{answer_id}/audio"
        )
        assert posted.status_code == 404

    async with client:
        user_message = await client.get(f"/api/v1/dialogs/{dialog_id}/messages/1/audio")
        missing = await client.get(f"/api/v1/dialogs/{dialog_id}/messages/999999/audio")
    assert user_message.status_code == 404
    assert missing.status_code == 404
    assert provider.calls == []


@pytest.mark.asyncio
async def test_audio_too_long_returns_422() -> None:
    client, dialog_id, answer_id, _, provider, _ = await make_client(max_text_chars=5)

    async with client:
        response = await client.post(
            f"/api/v1/dialogs/{dialog_id}/messages/{answer_id}/audio",
            json={"voice": "aidar"},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Answer is too long for voiceover."}
    assert provider.calls == []


@pytest.mark.asyncio
async def test_synthesis_failure_returns_safe_503() -> None:
    class FailingProvider(FakeSpeechProvider):
        async def synthesize(self, text: str, *, voice: str) -> bytes:
            raise RuntimeError("private details")

    client, dialog_id, answer_id, speech, _, _ = await make_client()
    speech._provider = FailingProvider()

    async with client:
        assert (
            await client.post(
                f"/api/v1/dialogs/{dialog_id}/messages/{answer_id}/audio",
                json={"voice": "aidar"},
            )
        ).status_code == 202
        await wait_for_audio(speech, answer_id, "aidar")
        response = await client.get(
            f"/api/v1/dialogs/{dialog_id}/messages/{answer_id}/audio?voice=aidar"
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Voiceover failed."}
    assert "private details" not in response.text


@pytest.mark.asyncio
async def test_audio_without_speech_service_is_503() -> None:
    history = InMemoryHistoryStore()
    dialog_id = await history.create(TEST_USER.id)
    _, answer_id = await history.append(
        dialog_id,
        (
            Message(role=MessageRole.USER, content="q"),
            Message(role=MessageRole.ASSISTANT, content="a"),
        ),
    )
    service = AgentService(EchoAgent(), history, InMemoryDialogEventBroker())
    app = create_app(service, auth_service=static_auth_service())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=AUTH_COOKIES,
    ) as client:
        response = await client.post(
            f"/api/v1/dialogs/{dialog_id}/messages/{answer_id}/audio"
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Voiceover is unavailable."}
