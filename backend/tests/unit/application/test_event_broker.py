import asyncio
import inspect
from uuid import uuid4

import pytest

from smeshariki_ai.application import (
    DialogEvent,
    DialogEventBroker,
    DialogEventType,
    InMemoryDialogEventBroker,
)


def test_dialog_event_broker_is_abstract() -> None:
    assert inspect.isabstract(DialogEventBroker)


@pytest.mark.parametrize("queue_size", [0, -1])
def test_in_memory_broker_requires_positive_queue_size(queue_size: int) -> None:
    with pytest.raises(ValueError, match="queue_size must be positive"):
        InMemoryDialogEventBroker(queue_size=queue_size)


@pytest.mark.asyncio
async def test_broadcasts_ordered_events_and_isolates_dialogs() -> None:
    broker = InMemoryDialogEventBroker()
    first_dialog_id = uuid4()
    second_dialog_id = uuid4()
    first = await broker.subscribe(first_dialog_id)
    second = await broker.subscribe(first_dialog_id)
    other = await broker.subscribe(second_dialog_id)
    start = DialogEvent(type=DialogEventType.MESSAGE_START)
    delta = DialogEvent(type=DialogEventType.MESSAGE_DELTA, delta="answer")
    end = DialogEvent(type=DialogEventType.MESSAGE_END)

    await broker.publish(first_dialog_id, start)
    await broker.publish(first_dialog_id, delta)
    await broker.publish(second_dialog_id, end)

    assert [await first.receive(), await first.receive()] == [start, delta]
    assert [await second.receive(), await second.receive()] == [start, delta]
    assert await other.receive() == end
    await broker.shutdown()


@pytest.mark.asyncio
async def test_does_not_replay_events_published_without_subscribers() -> None:
    broker = InMemoryDialogEventBroker()
    dialog_id = uuid4()
    old_event = DialogEvent(type=DialogEventType.MESSAGE_START)
    new_event = DialogEvent(type=DialogEventType.MESSAGE_END)

    await broker.publish(dialog_id, old_event)
    subscription = await broker.subscribe(dialog_id)
    await broker.publish(dialog_id, new_event)

    assert await subscription.receive() == new_event
    await broker.shutdown()


@pytest.mark.asyncio
async def test_overflow_closes_only_the_slow_subscriber() -> None:
    broker = InMemoryDialogEventBroker(queue_size=1)
    dialog_id = uuid4()
    slow = await broker.subscribe(dialog_id)
    active = await broker.subscribe(dialog_id)
    first = DialogEvent(type=DialogEventType.MESSAGE_START)
    second = DialogEvent(type=DialogEventType.MESSAGE_END)

    await broker.publish(dialog_id, first)
    assert await active.receive() == first
    await broker.publish(dialog_id, second)

    assert slow.closed
    assert await slow.receive() is None
    assert not active.closed
    assert await active.receive() == second
    await broker.shutdown()


@pytest.mark.asyncio
async def test_unsubscribe_is_idempotent_and_discards_pending_events() -> None:
    broker = InMemoryDialogEventBroker()
    dialog_id = uuid4()
    subscription = await broker.subscribe(dialog_id)
    await broker.publish(
        dialog_id,
        DialogEvent(type=DialogEventType.MESSAGE_START),
    )

    await broker.unsubscribe(subscription)
    await broker.unsubscribe(subscription)
    await broker.publish(
        dialog_id,
        DialogEvent(type=DialogEventType.MESSAGE_END),
    )

    assert subscription.closed
    assert await subscription.receive() is None
    await broker.shutdown()


@pytest.mark.asyncio
async def test_shutdown_is_idempotent_and_unblocks_receive() -> None:
    broker = InMemoryDialogEventBroker()
    subscription = await broker.subscribe(uuid4())
    pending_receive = asyncio.create_task(subscription.receive())
    await asyncio.sleep(0)

    await broker.shutdown()
    await broker.shutdown()

    assert await asyncio.wait_for(pending_receive, timeout=0.1) is None
    assert subscription.closed
    with pytest.raises(RuntimeError, match="broker is closed"):
        await broker.subscribe(uuid4())


@pytest.mark.asyncio
async def test_publish_after_shutdown_is_a_safe_noop() -> None:
    broker = InMemoryDialogEventBroker()
    dialog_id = uuid4()
    await broker.shutdown()

    await broker.publish(
        dialog_id,
        DialogEvent(type=DialogEventType.MESSAGE_START),
    )


@pytest.mark.asyncio
async def test_concurrent_operations_keep_subscribers_consistent() -> None:
    broker = InMemoryDialogEventBroker(queue_size=16)
    dialog_id = uuid4()
    subscriptions = await asyncio.gather(
        *(broker.subscribe(dialog_id) for _ in range(8))
    )
    events = [
        DialogEvent(type=DialogEventType.MESSAGE_DELTA, delta=str(index))
        for index in range(16)
    ]

    await asyncio.gather(*(broker.publish(dialog_id, event) for event in events))

    received = [
        [await subscription.receive() for _ in events] for subscription in subscriptions
    ]
    assert all(sequence == received[0] for sequence in received)
    assert {event.delta for event in received[0]} == {event.delta for event in events}

    await asyncio.gather(
        *(broker.unsubscribe(subscription) for subscription in subscriptions)
    )
    assert all(subscription.closed for subscription in subscriptions)
    await broker.shutdown()
