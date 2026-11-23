from dataclasses import dataclass
from enum import StrEnum


class SpeechStatus(StrEnum):
    """Lifecycle of one message voiceover."""

    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


AUDIO_MIME_TYPE = "audio/mpeg"


@dataclass(frozen=True, slots=True)
class AudioArtifact:
    """Encoded audio ready to be stored and returned to the browser."""

    data: bytes
    duration_ms: int
    mime_type: str = AUDIO_MIME_TYPE


@dataclass(frozen=True, slots=True)
class AudioRecord:
    """Persisted voiceover metadata of one assistant message and voice."""

    message_id: int
    voice_id: str
    status: SpeechStatus
    text_hash: str
    voice_version: str
    object_key: str | None = None
    size_bytes: int | None = None
    etag: str | None = None
    mime_type: str | None = None
    duration_ms: int | None = None
    audio_data: bytes | None = None
    error_code: str | None = None

    @property
    def has_audio(self) -> bool:
        return bool(self.object_key) and self.mime_type is not None


@dataclass(frozen=True, slots=True)
class AudioPayload:
    record: AudioRecord
    data: bytes
