import asyncio
from collections.abc import Collection

from smeshariki_ai.speech.models import AudioArtifact, AudioRecord, SpeechStatus
from smeshariki_ai.speech.store import MessageAudioStore


class InMemoryMessageAudioStore(MessageAudioStore):
    def __init__(self) -> None:
        self._records: dict[tuple[int, str], AudioRecord] = {}
        self._lock = asyncio.Lock()

    async def get(self, message_id: int, voice_id: str) -> AudioRecord | None:
        async with self._lock:
            return self._records.get((message_id, voice_id))

    async def ready_voices(
        self, message_ids: Collection[int]
    ) -> dict[int, frozenset[str]]:
        async with self._lock:
            ids = set(message_ids)
            result: dict[int, set[str]] = {}
            for (message_id, voice_id), record in self._records.items():
                if message_id in ids and record.has_audio:
                    result.setdefault(message_id, set()).add(voice_id)
            return {
                message_id: frozenset(voices) for message_id, voices in result.items()
            }

    async def object_keys(self, message_ids: Collection[int]) -> tuple[str, ...]:
        async with self._lock:
            ids = set(message_ids)
            return tuple(
                record.object_key
                for record in self._records.values()
                if record.message_id in ids and record.object_key is not None
            )

    async def start(
        self,
        message_id: int,
        voice_id: str,
        *,
        text_hash: str,
        voice_version: str,
    ) -> AudioRecord:
        async with self._lock:
            current = self._records.get((message_id, voice_id))
            if current is not None and current.status is SpeechStatus.PENDING:
                if (
                    current.text_hash == text_hash
                    and current.voice_version == voice_version
                ):
                    return current
            record = AudioRecord(
                message_id=message_id,
                voice_id=voice_id,
                status=SpeechStatus.PENDING,
                text_hash=text_hash,
                voice_version=voice_version,
                object_key=current.object_key if current else None,
                size_bytes=current.size_bytes if current else None,
                etag=current.etag if current else None,
                mime_type=current.mime_type if current else None,
                duration_ms=current.duration_ms if current else None,
                audio_data=current.audio_data if current else None,
            )
            self._records[(message_id, voice_id)] = record
            return record

    async def complete(
        self,
        message_id: int,
        voice_id: str,
        *,
        text_hash: str,
        voice_version: str,
        artifact: AudioArtifact,
        object_key: str,
        size_bytes: int,
        etag: str,
    ) -> AudioRecord | None:
        async with self._lock:
            current = self._records.get((message_id, voice_id))
            if not self._matches_pending(current, text_hash, voice_version):
                return None
            record = AudioRecord(
                message_id=message_id,
                voice_id=voice_id,
                status=SpeechStatus.READY,
                text_hash=text_hash,
                voice_version=voice_version,
                object_key=object_key,
                size_bytes=size_bytes,
                etag=etag,
                mime_type=artifact.mime_type,
                duration_ms=artifact.duration_ms,
            )
            self._records[(message_id, voice_id)] = record
            return record

    async def fail(
        self,
        message_id: int,
        voice_id: str,
        *,
        text_hash: str,
        voice_version: str,
        error_code: str,
    ) -> AudioRecord | None:
        async with self._lock:
            current = self._records.get((message_id, voice_id))
            if not self._matches_pending(current, text_hash, voice_version):
                return None
            status = (
                SpeechStatus.READY
                if current and current.object_key
                else SpeechStatus.FAILED
            )
            record = AudioRecord(
                message_id=message_id,
                voice_id=voice_id,
                status=status,
                text_hash=text_hash,
                voice_version=voice_version,
                object_key=current.object_key if current else None,
                size_bytes=current.size_bytes if current else None,
                etag=current.etag if current else None,
                mime_type=current.mime_type if current else None,
                duration_ms=current.duration_ms if current else None,
                audio_data=current.audio_data if current else None,
                error_code=error_code,
            )
            self._records[(message_id, voice_id)] = record
            return record

    async def reset_pending(self) -> int:
        async with self._lock:
            pending = [
                record
                for record in self._records.values()
                if record.status is SpeechStatus.PENDING
            ]
            for record in pending:
                self._records[(record.message_id, record.voice_id)] = AudioRecord(
                    message_id=record.message_id,
                    voice_id=record.voice_id,
                    status=(
                        SpeechStatus.READY if record.object_key else SpeechStatus.FAILED
                    ),
                    text_hash=record.text_hash,
                    voice_version=record.voice_version,
                    object_key=record.object_key,
                    size_bytes=record.size_bytes,
                    etag=record.etag,
                    mime_type=record.mime_type,
                    duration_ms=record.duration_ms,
                    audio_data=record.audio_data,
                    error_code=None if record.object_key else "interrupted",
                )
            return len(pending)

    async def legacy_records(self) -> tuple[AudioRecord, ...]:
        async with self._lock:
            return tuple(
                record
                for record in self._records.values()
                if record.audio_data is not None and record.object_key is None
            )

    async def clear_legacy_audio(
        self,
        message_id: int,
        voice_id: str,
        *,
        object_key: str,
        size_bytes: int,
        etag: str,
    ) -> None:
        async with self._lock:
            record = self._records.get((message_id, voice_id))
            if record is None:
                return
            self._records[(message_id, voice_id)] = AudioRecord(
                message_id=message_id,
                voice_id=voice_id,
                status=record.status,
                text_hash=record.text_hash,
                voice_version=record.voice_version,
                object_key=object_key,
                size_bytes=size_bytes,
                etag=etag,
                mime_type=record.mime_type,
                duration_ms=record.duration_ms,
                error_code=record.error_code,
            )

    @staticmethod
    def _matches_pending(
        record: AudioRecord | None,
        text_hash: str,
        voice_version: str,
    ) -> bool:
        return (
            record is not None
            and record.status is SpeechStatus.PENDING
            and record.text_hash == text_hash
            and record.voice_version == voice_version
        )
