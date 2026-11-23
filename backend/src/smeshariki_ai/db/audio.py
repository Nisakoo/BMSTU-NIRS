from collections.abc import Collection, Iterator
from contextlib import contextmanager

from asyncpg import PostgresError
from sqlalchemy import Row, case, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from smeshariki_ai.db.tables import message_audio
from smeshariki_ai.speech.errors import SpeechStoreUnavailableError
from smeshariki_ai.speech.models import AudioArtifact, AudioRecord, SpeechStatus
from smeshariki_ai.speech.store import MessageAudioStore


@contextmanager
def _unavailable_on_failure() -> Iterator[None]:
    try:
        yield
    except (SQLAlchemyError, PostgresError, OSError, TimeoutError) as error:
        raise SpeechStoreUnavailableError from error


class PostgresMessageAudioStore(MessageAudioStore):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get(self, message_id: int, voice_id: str) -> AudioRecord | None:
        with _unavailable_on_failure():
            async with self._engine.connect() as connection:
                row = (
                    await connection.execute(
                        select(message_audio).where(
                            message_audio.c.message_id == message_id,
                            message_audio.c.voice_id == voice_id,
                        )
                    )
                ).first()
        return None if row is None else _record(row)

    async def ready_voices(
        self, message_ids: Collection[int]
    ) -> dict[int, frozenset[str]]:
        ids = list(message_ids)
        if not ids:
            return {}
        statement = select(message_audio.c.message_id, message_audio.c.voice_id).where(
            message_audio.c.message_id.in_(ids),
            message_audio.c.object_key.is_not(None),
        )
        with _unavailable_on_failure():
            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement)).all()
        result: dict[int, set[str]] = {}
        for row in rows:
            result.setdefault(row.message_id, set()).add(row.voice_id)
        return {message_id: frozenset(voices) for message_id, voices in result.items()}

    async def object_keys(self, message_ids: Collection[int]) -> tuple[str, ...]:
        ids = list(message_ids)
        if not ids:
            return ()
        statement = select(message_audio.c.object_key).where(
            message_audio.c.message_id.in_(ids),
            message_audio.c.object_key.is_not(None),
        )
        with _unavailable_on_failure():
            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement)).scalars().all()
        return tuple(row for row in rows if row is not None)

    async def start(
        self,
        message_id: int,
        voice_id: str,
        *,
        text_hash: str,
        voice_version: str,
    ) -> AudioRecord:
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                await connection.execute(
                    pg_insert(message_audio)
                    .values(
                        message_id=message_id,
                        voice_id=voice_id,
                        status=SpeechStatus.PENDING.value,
                        text_hash=text_hash,
                        voice_version=voice_version,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            message_audio.c.message_id,
                            message_audio.c.voice_id,
                        ]
                    )
                )
                row = (
                    await connection.execute(
                        select(message_audio)
                        .where(
                            message_audio.c.message_id == message_id,
                            message_audio.c.voice_id == voice_id,
                        )
                        .with_for_update()
                    )
                ).first()
                assert row is not None
                current = _record(row)
                if (
                    current.status is SpeechStatus.PENDING
                    and current.text_hash == text_hash
                    and current.voice_version == voice_version
                ):
                    return current
                updated = (
                    await connection.execute(
                        update(message_audio)
                        .where(
                            message_audio.c.message_id == message_id,
                            message_audio.c.voice_id == voice_id,
                        )
                        .values(
                            status=SpeechStatus.PENDING.value,
                            text_hash=text_hash,
                            voice_version=voice_version,
                            error_code=None,
                            updated_at=func.now(),
                        )
                        .returning(message_audio)
                    )
                ).first()
                assert updated is not None
        return _record(updated)

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
        statement = (
            update(message_audio)
            .where(*_matching_pending(message_id, voice_id, text_hash, voice_version))
            .values(
                status=SpeechStatus.READY.value,
                object_key=object_key,
                size_bytes=size_bytes,
                etag=etag,
                mime_type=artifact.mime_type,
                duration_ms=artifact.duration_ms,
                audio_data=None,
                error_code=None,
                updated_at=func.now(),
            )
            .returning(message_audio)
        )
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                row = (await connection.execute(statement)).first()
        return None if row is None else _record(row)

    async def fail(
        self,
        message_id: int,
        voice_id: str,
        *,
        text_hash: str,
        voice_version: str,
        error_code: str,
    ) -> AudioRecord | None:
        statement = (
            update(message_audio)
            .where(*_matching_pending(message_id, voice_id, text_hash, voice_version))
            .values(
                status=case(
                    (message_audio.c.object_key.is_not(None), SpeechStatus.READY.value),
                    else_=SpeechStatus.FAILED.value,
                ),
                error_code=error_code,
                updated_at=func.now(),
            )
            .returning(message_audio)
        )
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                row = (await connection.execute(statement)).first()
        return None if row is None else _record(row)

    async def reset_pending(self) -> int:
        statement = (
            update(message_audio)
            .where(message_audio.c.status == SpeechStatus.PENDING.value)
            .values(
                status=case(
                    (message_audio.c.object_key.is_not(None), SpeechStatus.READY.value),
                    else_=SpeechStatus.FAILED.value,
                ),
                error_code=case(
                    (message_audio.c.object_key.is_not(None), None),
                    else_="interrupted",
                ),
                updated_at=func.now(),
            )
        )
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                result = await connection.execute(statement)
        return result.rowcount

    async def legacy_records(self) -> tuple[AudioRecord, ...]:
        statement = select(message_audio).where(
            message_audio.c.audio_data.is_not(None),
            message_audio.c.object_key.is_(None),
        )
        with _unavailable_on_failure():
            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement)).all()
        return tuple(_record(row) for row in rows)

    async def clear_legacy_audio(
        self,
        message_id: int,
        voice_id: str,
        *,
        object_key: str,
        size_bytes: int,
        etag: str,
    ) -> None:
        statement = (
            update(message_audio)
            .where(
                message_audio.c.message_id == message_id,
                message_audio.c.voice_id == voice_id,
            )
            .values(
                object_key=object_key,
                size_bytes=size_bytes,
                etag=etag,
                audio_data=None,
                updated_at=func.now(),
            )
        )
        with _unavailable_on_failure():
            async with self._engine.begin() as connection:
                await connection.execute(statement)


def _matching_pending(
    message_id: int,
    voice_id: str,
    text_hash: str,
    voice_version: str,
) -> tuple[object, ...]:
    return (
        message_audio.c.message_id == message_id,
        message_audio.c.voice_id == voice_id,
        message_audio.c.status == SpeechStatus.PENDING.value,
        message_audio.c.text_hash == text_hash,
        message_audio.c.voice_version == voice_version,
    )


def _record(row: Row) -> AudioRecord:  # type: ignore[type-arg]
    return AudioRecord(
        message_id=row.message_id,
        voice_id=row.voice_id,
        status=SpeechStatus(row.status),
        text_hash=row.text_hash,
        voice_version=row.voice_version,
        object_key=row.object_key,
        size_bytes=row.size_bytes,
        etag=row.etag,
        mime_type=row.mime_type,
        duration_ms=row.duration_ms,
        audio_data=bytes(row.audio_data) if row.audio_data is not None else None,
        error_code=row.error_code,
    )
