import asyncio
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from smeshariki_ai.agent import Message
from smeshariki_ai.dialogs.errors import DialogNotFoundError
from smeshariki_ai.dialogs.models import (
    DialogCursor,
    DialogSummary,
    DialogTranscript,
    StoredMessage,
)


class HistoryStore(ABC):
    """Persistent dialogs; a dialog exists only together with its first messages."""

    @abstractmethod
    async def create(
        self,
        dialog_id: UUID,
        owner_id: UUID,
        title: str | None,
        messages: Sequence[Message],
        now: datetime,
    ) -> None:
        """Atomically store a new dialog together with its first messages."""

    @abstractmethod
    async def owner(self, dialog_id: UUID) -> UUID:
        """Return the owner of a dialog or raise ``DialogNotFoundError``."""

    @abstractmethod
    async def get(self, dialog_id: UUID) -> tuple[Message, ...]:
        """Return an immutable snapshot of a dialog history."""

    @abstractmethod
    async def read(self, dialog_id: UUID) -> DialogTranscript:
        """Return the title and timestamped messages of a dialog."""

    @abstractmethod
    async def append(
        self,
        dialog_id: UUID,
        messages: Sequence[Message],
        now: datetime,
    ) -> None:
        """Atomically append a group of messages to a dialog."""

    @abstractmethod
    async def list(
        self,
        owner_id: UUID,
        limit: int,
        after: DialogCursor | None,
    ) -> tuple[DialogSummary, ...]:
        """Return up to ``limit`` dialogs of an owner, newest activity first."""

    @abstractmethod
    async def delete(self, dialog_id: UUID) -> None:
        """Delete a dialog with its messages or raise ``DialogNotFoundError``."""


@dataclass
class _Dialog:
    owner_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime
    messages: list[tuple[Message, datetime]] = field(default_factory=list)


class InMemoryHistoryStore(HistoryStore):
    def __init__(self) -> None:
        self._dialogs: dict[UUID, _Dialog] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        dialog_id: UUID,
        owner_id: UUID,
        title: str | None,
        messages: Sequence[Message],
        now: datetime,
    ) -> None:
        async with self._lock:
            if dialog_id in self._dialogs:
                raise ValueError("Dialog already exists.")
            self._dialogs[dialog_id] = _Dialog(
                owner_id=owner_id,
                title=title,
                created_at=now,
                updated_at=now,
                messages=[(message, now) for message in messages],
            )

    async def owner(self, dialog_id: UUID) -> UUID:
        async with self._lock:
            return self._find(dialog_id).owner_id

    async def get(self, dialog_id: UUID) -> tuple[Message, ...]:
        async with self._lock:
            dialog = self._find(dialog_id)
            return tuple(message for message, _ in dialog.messages)

    async def read(self, dialog_id: UUID) -> DialogTranscript:
        async with self._lock:
            dialog = self._find(dialog_id)
            return DialogTranscript(
                title=dialog.title,
                messages=tuple(
                    StoredMessage(
                        role=message.role,
                        content=message.content,
                        created_at=created_at,
                    )
                    for message, created_at in dialog.messages
                ),
            )

    async def append(
        self,
        dialog_id: UUID,
        messages: Sequence[Message],
        now: datetime,
    ) -> None:
        async with self._lock:
            dialog = self._find(dialog_id)
            dialog.messages.extend((message, now) for message in messages)
            dialog.updated_at = now

    async def list(
        self,
        owner_id: UUID,
        limit: int,
        after: DialogCursor | None,
    ) -> tuple[DialogSummary, ...]:
        async with self._lock:
            summaries = [
                DialogSummary(
                    dialog_id=dialog_id,
                    title=dialog.title,
                    created_at=dialog.created_at,
                    updated_at=dialog.updated_at,
                )
                for dialog_id, dialog in self._dialogs.items()
                if dialog.owner_id == owner_id
            ]
        if after is not None:
            summaries = [
                summary
                for summary in summaries
                if (summary.updated_at, summary.dialog_id)
                < (after.updated_at, after.dialog_id)
            ]
        summaries.sort(key=lambda item: (item.updated_at, item.dialog_id), reverse=True)
        return tuple(summaries[:limit])

    async def delete(self, dialog_id: UUID) -> None:
        async with self._lock:
            self._find(dialog_id)
            del self._dialogs[dialog_id]

    def _find(self, dialog_id: UUID) -> _Dialog:
        try:
            return self._dialogs[dialog_id]
        except KeyError as error:
            raise DialogNotFoundError(dialog_id) from error
