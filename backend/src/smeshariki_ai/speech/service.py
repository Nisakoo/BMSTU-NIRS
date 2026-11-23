import asyncio
import hashlib
import logging
import time
from collections.abc import Collection
from uuid import UUID, uuid4

from smeshariki_ai.dialogs import HistoryStore, StoredMessage
from smeshariki_ai.observability import log_event, utc_now
from smeshariki_ai.speech.config import SILERO_VOICES, SpeechConfig
from smeshariki_ai.speech.encoder import (
    AudioEncoder,
    join_wav_chunks,
    wav_duration_ms,
)
from smeshariki_ai.speech.errors import (
    SpeechObjectStoreError,
    SpeechStoreUnavailableError,
    SpeechSynthesisError,
    SpeechTextTooLongError,
    SpeechUnavailableError,
    SpeechVoiceError,
)
from smeshariki_ai.speech.models import (
    AudioArtifact,
    AudioPayload,
    AudioRecord,
)
from smeshariki_ai.speech.normalize import NORMALIZATION_VERSION, split_for_speech
from smeshariki_ai.speech.objects import AudioObjectStore
from smeshariki_ai.speech.provider import SpeechProvider
from smeshariki_ai.speech.store import MessageAudioStore

logger = logging.getLogger(__name__)


class NarratorSpeechService:
    """Coordinate per-voice local voiceovers stored as Ceph objects."""

    def __init__(
        self,
        history_store: HistoryStore,
        audio_store: MessageAudioStore,
        object_store: AudioObjectStore,
        provider: SpeechProvider,
        encoder: AudioEncoder,
        config: SpeechConfig,
        *,
        object_prefix: str = "smeshariki-audio",
    ) -> None:
        self._history_store = history_store
        self._audio_store = audio_store
        self._object_store = object_store
        self._provider = provider
        self._encoder = encoder
        self._config = config
        self._object_prefix = object_prefix.strip("/")
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self._message_locks: dict[tuple[int, str], asyncio.Lock] = {}
        self._tasks: dict[tuple[int, str], asyncio.Task[None]] = {}
        self._state_lock = asyncio.Lock()
        self._closed = False

    def voice_version(self, voice_id: str) -> str:
        return (
            f"{self._provider.model_version}:{voice_id}:"
            f"{self._config.speed:.3f}:{NORMALIZATION_VERSION}"
        )

    async def startup(self) -> None:
        try:
            await self._object_store.startup()
        except SpeechObjectStoreError:
            log_event(
                logger,
                logging.WARNING,
                "speech.objects.startup_failed",
                outcome="failed",
                error_type="SpeechObjectStoreError",
            )
        await self._backfill_legacy()
        try:
            count = await self._audio_store.reset_pending()
        except SpeechStoreUnavailableError:
            log_event(
                logger,
                logging.WARNING,
                "speech.store.reset_failed",
                outcome="failed",
                error_type="SpeechStoreUnavailableError",
            )
            return
        if count:
            log_event(
                logger,
                logging.INFO,
                "speech.pending.interrupted",
                count=count,
                outcome="interrupted",
            )

    async def delete_dialog_audio(self, user_id: UUID, dialog_id: UUID) -> None:
        try:
            transcript = await self._history_store.transcript(user_id, dialog_id)
            ids = [
                item.id
                for item in transcript.messages
                if item.role.value == "assistant"
            ]
            keys = await self._audio_store.object_keys(ids)
            for key in keys:
                await self._object_store.delete(key)
        except (SpeechStoreUnavailableError, SpeechObjectStoreError):
            log_event(
                logger,
                logging.WARNING,
                "speech.objects.delete_failed",
                outcome="failed",
            )

    async def shutdown(self) -> None:
        async with self._state_lock:
            self._closed = True
            tasks = tuple(self._tasks.values())
            for task in tasks:
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def request(
        self,
        user_id: UUID,
        dialog_id: UUID,
        message_id: int,
        voice_id: str | None = None,
    ) -> AudioRecord:
        voice = self._voice(voice_id)
        message = await self._history_store.get_message(user_id, dialog_id, message_id)
        if len(message.content) > self._config.max_text_chars:
            raise SpeechTextTooLongError("The answer is too long for voiceover.")
        text_hash = _text_hash(message.content)
        voice_version = self.voice_version(voice)

        key = (message_id, voice)
        async with self._message_lock(key):
            self._ensure_open()
            record = await self._audio_store.start(
                message_id,
                voice,
                text_hash=text_hash,
                voice_version=voice_version,
            )
            task = self._tasks.get(key)
            if task is None or task.done():
                task = asyncio.create_task(
                    self._generate(
                        message,
                        dialog_id,
                        voice,
                        text_hash,
                        voice_version,
                        record.object_key,
                    ),
                    name=f"speech-message-{message_id}-{voice}",
                )
                self._tasks[key] = task
                task.add_done_callback(
                    lambda completed, current_key=key: self._task_done(
                        current_key, completed
                    )
                )
            return record

    async def get(
        self,
        user_id: UUID,
        dialog_id: UUID,
        message_id: int,
        voice_id: str | None = None,
    ) -> AudioPayload | None:
        voice = self._voice(voice_id)
        await self._history_store.get_message(user_id, dialog_id, message_id)
        record = await self._audio_store.get(message_id, voice)
        if record is None or record.object_key is None:
            return AudioPayload(record, b"") if record is not None else None
        data = await self._object_store.get(record.object_key)
        return AudioPayload(record, data)

    async def available_voices(
        self, message_ids: Collection[int]
    ) -> dict[int, frozenset[str]]:
        try:
            return await self._audio_store.ready_voices(message_ids)
        except SpeechStoreUnavailableError:
            log_event(
                logger,
                logging.WARNING,
                "speech.availability.failed",
                outcome="failed",
                error_type="SpeechStoreUnavailableError",
            )
            return {}

    async def _generate(
        self,
        message: StoredMessage,
        dialog_id: UUID,
        voice: str,
        text_hash: str,
        voice_version: str,
        previous_object_key: str | None,
    ) -> None:
        started_at = utc_now()
        started = time.monotonic()
        message_id = message.id
        new_object_key = self._object_key(dialog_id, message_id, voice, str(uuid4()))
        log_event(
            logger,
            logging.INFO,
            "speech.synthesis.started",
            message_id=message_id,
            char_count=len(message.content),
            outcome="started",
        )
        try:
            async with self._semaphore:
                chunks = split_for_speech(
                    message.content,
                    max_chars=min(self._config.max_text_chars, 800),
                )
                if not chunks:
                    raise SpeechSynthesisError("The answer has no speech.")
                wavs = [
                    await self._provider.synthesize(chunk.text, voice=voice)
                    for chunk in chunks
                ]
                joined = join_wav_chunks(
                    wavs,
                    [chunk.pause_after_ms for chunk in chunks],
                )
                duration_ms = round(wav_duration_ms(joined) / self._config.speed)
                mp3 = await asyncio.to_thread(
                    self._encoder.to_mp3,
                    joined,
                    speed=self._config.speed,
                )
                info = await self._object_store.put(
                    new_object_key,
                    mp3,
                    content_type="audio/mpeg",
                )
                completed = await self._audio_store.complete(
                    message_id,
                    voice,
                    text_hash=text_hash,
                    voice_version=voice_version,
                    artifact=AudioArtifact(data=mp3, duration_ms=duration_ms),
                    object_key=new_object_key,
                    size_bytes=info.size,
                    etag=info.etag,
                )
                if completed is None:
                    await self._object_store.delete(new_object_key)
                    return
                if previous_object_key and previous_object_key != new_object_key:
                    await self._object_store.delete(previous_object_key)
            log_event(
                logger,
                logging.INFO,
                "speech.synthesis.completed",
                message_id=message_id,
                char_count=len(message.content),
                started_at=started_at,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                outcome="completed",
            )
        except asyncio.CancelledError:
            log_event(
                logger,
                logging.INFO,
                "speech.synthesis.cancelled",
                message_id=message_id,
                char_count=len(message.content),
                started_at=started_at,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                outcome="cancelled",
            )
            raise
        except Exception as error:
            await self._object_store.delete(new_object_key)
            try:
                await self._audio_store.fail(
                    message_id,
                    voice,
                    text_hash=text_hash,
                    voice_version=voice_version,
                    error_code="synthesis_failed",
                )
            except SpeechStoreUnavailableError:
                pass
            log_event(
                logger,
                logging.ERROR,
                "speech.synthesis.failed",
                message_id=message_id,
                char_count=len(message.content),
                started_at=started_at,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                outcome="failed",
                error_type=type(error).__name__,
            )

    async def _backfill_legacy(self) -> None:
        try:
            legacy = await self._audio_store.legacy_records()
        except SpeechStoreUnavailableError:
            return
        for record in legacy:
            key = self._object_key(0, record.message_id, record.voice_id, "legacy")
            try:
                data = record.audio_data
                if data is None:
                    continue
                info = await self._object_store.put(
                    key,
                    data,
                    content_type=record.mime_type or "audio/mpeg",
                )
                await self._audio_store.clear_legacy_audio(
                    record.message_id,
                    record.voice_id,
                    object_key=key,
                    size_bytes=info.size,
                    etag=info.etag,
                )
            except (SpeechObjectStoreError, SpeechStoreUnavailableError):
                log_event(
                    logger,
                    logging.WARNING,
                    "speech.legacy.backfill_failed",
                    message_id=record.message_id,
                    outcome="failed",
                )

    def _voice(self, voice_id: str | None) -> str:
        voice = self._config.voice if voice_id is None else voice_id
        if voice not in SILERO_VOICES:
            raise SpeechVoiceError("Unknown narrator voice.")
        return voice

    def _object_key(
        self,
        dialog_id: UUID | int,
        message_id: int,
        voice: str,
        generation_id: str,
    ) -> str:
        return (
            f"{self._object_prefix}/{dialog_id}/{message_id}/{voice}/"
            f"{generation_id}.mp3"
        )

    def _message_lock(self, key: tuple[int, str]) -> asyncio.Lock:
        lock = self._message_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._message_locks[key] = lock
        return lock

    def _task_done(self, key: tuple[int, str], task: asyncio.Task[None]) -> None:
        if self._tasks.get(key) is task:
            self._tasks.pop(key, None)
        try:
            task.exception()
        except asyncio.CancelledError:
            pass

    def _ensure_open(self) -> None:
        if self._closed:
            raise SpeechUnavailableError("Voiceover service is not accepting work.")


def _text_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
