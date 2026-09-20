import asyncio
from abc import ABC, abstractmethod
from uuid import UUID

from smeshariki_ai.application.events import DialogEvent, DialogSubscription

_CLOSED = object()


class DialogEventBroker(ABC):
    @abstractmethod
    async def subscribe(self, dialog_id: UUID) -> DialogSubscription:
        """Open a subscription for future events of one dialog."""

    @abstractmethod
    async def unsubscribe(self, subscription: DialogSubscription) -> None:
        """Close a subscription and release its resources."""

    @abstractmethod
    async def publish(self, dialog_id: UUID, event: DialogEvent) -> None:
        """Publish an event to active subscribers of one dialog."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Close the broker and all active subscriptions."""


class _InMemoryDialogSubscription:
    def __init__(self, dialog_id: UUID, queue_size: int) -> None:
        self._dialog_id = dialog_id
        self._queue: asyncio.Queue[DialogEvent | object] = asyncio.Queue(queue_size)
        self._closed = False

    @property
    def dialog_id(self) -> UUID:
        return self._dialog_id

    @property
    def closed(self) -> bool:
        return self._closed

    async def receive(self) -> DialogEvent | None:
        item = await self._queue.get()
        if item is _CLOSED:
            return None
        assert isinstance(item, DialogEvent)
        return item

    def offer(self, event: DialogEvent) -> bool:
        if self._closed:
            return False
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self.close()
            return False
        return True

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


class InMemoryDialogEventBroker(DialogEventBroker):
    def __init__(self, *, queue_size: int = 64) -> None:
        if queue_size <= 0:
            raise ValueError("queue_size must be positive")
        self._queue_size = queue_size
        self._subscribers: dict[UUID, set[_InMemoryDialogSubscription]] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def subscribe(self, dialog_id: UUID) -> DialogSubscription:
        async with self._lock:
            if self._closed:
                raise RuntimeError("Dialog event broker is closed.")
            subscription = _InMemoryDialogSubscription(dialog_id, self._queue_size)
            self._subscribers.setdefault(dialog_id, set()).add(subscription)
            return subscription

    async def unsubscribe(self, subscription: DialogSubscription) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(subscription.dialog_id)
            if subscribers is None:
                return
            matched = next(
                (candidate for candidate in subscribers if candidate is subscription),
                None,
            )
            if matched is None:
                return
            subscribers.remove(matched)
            if not subscribers:
                self._subscribers.pop(subscription.dialog_id, None)
            matched.close()

    async def publish(self, dialog_id: UUID, event: DialogEvent) -> None:
        async with self._lock:
            if self._closed:
                return
            subscribers = self._subscribers.get(dialog_id)
            if not subscribers:
                return
            closed = {
                subscription
                for subscription in subscribers
                if not subscription.offer(event)
            }
            subscribers.difference_update(closed)
            if not subscribers:
                self._subscribers.pop(dialog_id, None)

    async def shutdown(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            subscriptions = tuple(
                subscription
                for subscribers in self._subscribers.values()
                for subscription in subscribers
            )
            self._subscribers.clear()
            for subscription in subscriptions:
                subscription.close(discard_pending=False)
