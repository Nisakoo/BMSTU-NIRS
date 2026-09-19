import asyncio
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DialogEventType(StrEnum):
    MESSAGE_START = "message_start"
    MESSAGE_DELTA = "message_delta"
    MESSAGE_END = "message_end"
    MESSAGE_ERROR = "message_error"


class DialogEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: DialogEventType
    delta: str | None = None
    code: str | None = None
    message: str | None = None


_CLOSED = object()


class DialogSubscription:
    def __init__(self, dialog_id: UUID, queue_size: int) -> None:
        self.dialog_id = dialog_id
        self._queue: asyncio.Queue[DialogEvent | object] = asyncio.Queue(queue_size)
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def offer(self, event: DialogEvent) -> bool:
        if self._closed:
            return False
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self.close()
            return False
        return True

    async def receive(self) -> DialogEvent | None:
        item = await self._queue.get()
        if item is _CLOSED:
            return None
        assert isinstance(item, DialogEvent)
        return item

    def close(self, *, discard_pending: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        if discard_pending:
            while not self._queue.empty():
                self._queue.get_nowait()
        elif self._queue.full():
            self._queue.get_nowait()
        self._queue.put_nowait(_CLOSED)
