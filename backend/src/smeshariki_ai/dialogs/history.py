import asyncio
from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID, uuid4

from smeshariki_ai.agent import Message
from smeshariki_ai.dialogs.errors import DialogNotFoundError


class HistoryStore(ABC):
    @abstractmethod
    async def create(self, owner_id: UUID) -> UUID:
        """Create an empty dialog owned by a user and return its identifier."""

    @abstractmethod
    async def owner(self, dialog_id: UUID) -> UUID:
        """Return the owner of a dialog or raise ``DialogNotFoundError``."""

    @abstractmethod
    async def get(self, dialog_id: UUID) -> tuple[Message, ...]:
        """Return an immutable snapshot of a dialog history."""

    @abstractmethod
    async def append(
        self,
        dialog_id: UUID,
        messages: Sequence[Message],
    ) -> None:
        """Atomically append a group of messages to a dialog."""


class InMemoryHistoryStore(HistoryStore):
    def __init__(self) -> None:
        self._histories: dict[UUID, list[Message]] = {}
        self._owners: dict[UUID, UUID] = {}
        self._lock = asyncio.Lock()

    async def create(self, owner_id: UUID) -> UUID:
        async with self._lock:
            dialog_id = uuid4()
            while dialog_id in self._histories:
                dialog_id = uuid4()
            self._histories[dialog_id] = []
            self._owners[dialog_id] = owner_id
            return dialog_id

    async def owner(self, dialog_id: UUID) -> UUID:
        async with self._lock:
            try:
                return self._owners[dialog_id]
            except KeyError as error:
                raise DialogNotFoundError(dialog_id) from error

    async def get(self, dialog_id: UUID) -> tuple[Message, ...]:
        async with self._lock:
            try:
                history = self._histories[dialog_id]
            except KeyError as error:
                raise DialogNotFoundError(dialog_id) from error
            return tuple(history)

    async def append(
        self,
        dialog_id: UUID,
        messages: Sequence[Message],
    ) -> None:
        async with self._lock:
            try:
                history = self._histories[dialog_id]
            except KeyError as error:
                raise DialogNotFoundError(dialog_id) from error
            history.extend(messages)
