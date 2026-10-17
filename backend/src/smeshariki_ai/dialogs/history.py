import asyncio
import itertools
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from smeshariki_ai.agent import Message, MessageRole
from smeshariki_ai.dialogs.errors import DialogNotFoundError, MessageNotFoundError
from smeshariki_ai.dialogs.models import (
    DialogSummary,
    DialogTranscript,
    StoredMessage,
    dialog_title,
)


class HistoryStore(ABC):
    """Dialogs owned by users; a foreign dialog is reported as missing."""

    @abstractmethod
    async def create(self, owner_id: UUID) -> UUID:
        """Create an empty dialog owned by the user and return its identifier."""

    @abstractmethod
    async def get(self, owner_id: UUID, dialog_id: UUID) -> tuple[Message, ...]:
        """Return an immutable snapshot of a dialog history."""

    @abstractmethod
    async def append(
        self,
        dialog_id: UUID,
        messages: Sequence[Message],
    ) -> tuple[int, ...]:
        """Atomically append messages and return their ids in order.

        The first user message names the dialog.
        """

    @abstractmethod
    async def list_dialogs(
        self, owner_id: UUID, *, limit: int
    ) -> tuple[DialogSummary, ...]:
        """Return non-empty dialogs of the user, most recently updated first."""

    @abstractmethod
    async def transcript(self, owner_id: UUID, dialog_id: UUID) -> DialogTranscript:
        """Return the title and the stored messages of a dialog."""

    @abstractmethod
    async def set_feedback(
        self,
        owner_id: UUID,
        dialog_id: UUID,
        message_id: int,
        score: int,
    ) -> None:
        """Rate an assistant answer in the user's own dialog with 1 to 5."""

    @abstractmethod
    async def clear_feedback(
        self, owner_id: UUID, dialog_id: UUID, message_id: int
    ) -> None:
        """Remove the rating of an answer; removing a missing rating is a no-op."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class _Dialog:
    owner_id: UUID
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    messages: list[StoredMessage] = field(default_factory=list)


class InMemoryHistoryStore(HistoryStore):
    def __init__(self, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._dialogs: dict[UUID, _Dialog] = {}
        self._feedback: dict[int, int] = {}
        self._message_ids = itertools.count(1)
        self._clock = clock
        self._lock = asyncio.Lock()

    async def create(self, owner_id: UUID) -> UUID:
        async with self._lock:
            dialog_id = uuid4()
            while dialog_id in self._dialogs:
                dialog_id = uuid4()
            now = self._clock()
            self._dialogs[dialog_id] = _Dialog(
                owner_id=owner_id, created_at=now, updated_at=now
            )
            return dialog_id

    async def get(self, owner_id: UUID, dialog_id: UUID) -> tuple[Message, ...]:
        async with self._lock:
            dialog = self._owned(owner_id, dialog_id)
            return tuple(
                Message(role=item.role, content=item.content)
                for item in dialog.messages
            )

    async def append(
        self,
        dialog_id: UUID,
        messages: Sequence[Message],
    ) -> tuple[int, ...]:
        async with self._lock:
            try:
                dialog = self._dialogs[dialog_id]
            except KeyError as error:
                raise DialogNotFoundError(dialog_id) from error
            now = self._clock()
            stored = [
                StoredMessage(
                    id=next(self._message_ids),
                    role=item.role,
                    content=item.content,
                    created_at=now,
                )
                for item in messages
            ]
            dialog.messages.extend(stored)
            if dialog.title is None:
                dialog.title = next(
                    (
                        dialog_title(item.content)
                        for item in messages
                        if item.role is MessageRole.USER
                    ),
                    None,
                )
            dialog.updated_at = now
            return tuple(item.id for item in stored)

    async def list_dialogs(
        self, owner_id: UUID, *, limit: int
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
                if dialog.owner_id == owner_id and dialog.messages
            ]
        summaries.sort(key=lambda summary: summary.updated_at, reverse=True)
        return tuple(summaries[:limit])

    async def transcript(self, owner_id: UUID, dialog_id: UUID) -> DialogTranscript:
        async with self._lock:
            dialog = self._owned(owner_id, dialog_id)
            return DialogTranscript(
                dialog_id=dialog_id,
                title=dialog.title,
                messages=tuple(
                    replace(item, feedback=self._feedback.get(item.id))
                    for item in dialog.messages
                ),
            )

    async def set_feedback(
        self,
        owner_id: UUID,
        dialog_id: UUID,
        message_id: int,
        score: int,
    ) -> None:
        async with self._lock:
            self._answer(owner_id, dialog_id, message_id)
            self._feedback[message_id] = score

    async def clear_feedback(
        self, owner_id: UUID, dialog_id: UUID, message_id: int
    ) -> None:
        async with self._lock:
            self._answer(owner_id, dialog_id, message_id)
            self._feedback.pop(message_id, None)

    def _answer(self, owner_id: UUID, dialog_id: UUID, message_id: int) -> None:
        dialog = self._dialogs.get(dialog_id)
        if (
            dialog is None
            or dialog.owner_id != owner_id
            or not any(
                item.id == message_id and item.role is MessageRole.ASSISTANT
                for item in dialog.messages
            )
        ):
            raise MessageNotFoundError(dialog_id, message_id)

    def _owned(self, owner_id: UUID, dialog_id: UUID) -> _Dialog:
        dialog = self._dialogs.get(dialog_id)
        if dialog is None or dialog.owner_id != owner_id:
            raise DialogNotFoundError(dialog_id)
        return dialog
