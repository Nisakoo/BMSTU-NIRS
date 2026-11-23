from abc import ABC, abstractmethod
from collections.abc import Collection

from smeshariki_ai.speech.models import AudioArtifact, AudioRecord


class MessageAudioStore(ABC):
    """Voiceover metadata keyed by assistant message and narrator voice."""

    @abstractmethod
    async def get(self, message_id: int, voice_id: str) -> AudioRecord | None: ...

    @abstractmethod
    async def ready_voices(
        self, message_ids: Collection[int]
    ) -> dict[int, frozenset[str]]:
        """Return voices with an existing Ceph object for each message."""

    @abstractmethod
    async def object_keys(self, message_ids: Collection[int]) -> tuple[str, ...]:
        """Return Ceph keys belonging to the messages."""

    @abstractmethod
    async def start(
        self,
        message_id: int,
        voice_id: str,
        *,
        text_hash: str,
        voice_version: str,
    ) -> AudioRecord:
        """Mark a new generation pending without forgetting the previous object."""

    @abstractmethod
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
    ) -> AudioRecord | None: ...

    @abstractmethod
    async def fail(
        self,
        message_id: int,
        voice_id: str,
        *,
        text_hash: str,
        voice_version: str,
        error_code: str,
    ) -> AudioRecord | None: ...

    @abstractmethod
    async def reset_pending(self) -> int: ...

    @abstractmethod
    async def legacy_records(self) -> tuple[AudioRecord, ...]:
        """Rows whose bytes still live in PostgreSQL and need a Ceph upload."""

    @abstractmethod
    async def clear_legacy_audio(
        self,
        message_id: int,
        voice_id: str,
        *,
        object_key: str,
        size_bytes: int,
        etag: str,
    ) -> None: ...
