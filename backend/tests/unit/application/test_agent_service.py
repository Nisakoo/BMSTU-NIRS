import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from smeshariki_ai.agent import (
    AgentResponse,
    AgentStreamEvent,
    AgentTextDelta,
    Message,
    MessageRole,
    UserRequest,
)
from smeshariki_ai.application import (
    AgentService,
    AgentServiceUnavailableError,
    DialogEvent,
    DialogEventType,
)
from smeshariki_ai.dialogs import (
    DialogNotFoundError,
    InMemoryHistoryStore,
)


@dataclass
class RunControl:
    response: str = "answer"
    error: Exception | None = None
    started: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)


class ControlledAgent:
    def __init__(self, controls: dict[str, RunControl]) -> None:
        self._controls = controls
        self.calls: list[tuple[tuple[Message, ...], UserRequest]] = []

    async def run(
        self,
        history: Sequence[Message],
        request: UserRequest,
    ) -> AsyncIterator[AgentStreamEvent]:
        self.calls.append((tuple(history), request))
        control = self._controls[request.content]
        control.started.set()
        try:
            await control.release.wait()
        except asyncio.CancelledError:
            control.cancelled.set()
            raise
        if control.error is not None:
            raise control.error
        if control.response:
            yield AgentTextDelta(content=control.response)
        yield AgentResponse(content=control.response)


class PartiallyFailingAgent:
    async def run(
        self,
        history: Sequence[Message],
        request: UserRequest,
    ) -> AsyncIterator[AgentStreamEvent]:
        yield AgentTextDelta(content="private partial response")
        raise RuntimeError("private failure detail")


async def wait_for_history_size(
    store: InMemoryHistoryStore,
    dialog_id: UUID,
    expected_size: int,
) -> tuple[Message, ...]:
    async def wait() -> tuple[Message, ...]:
        while True:
            history = await store.get(dialog_id)
            if len(history) == expected_size:
                return history
            await asyncio.sleep(0)

    return await asyncio.wait_for(wait(), timeout=1)


@pytest.mark.asyncio
async def test_start_dialog_delegates_to_history_store() -> None:
    store = InMemoryHistoryStore()
    service = AgentService(ControlledAgent({}), store)

    dialog_id = await service.start_dialog()

    assert dialog_id.version == 4
    assert await store.get(dialog_id) == ()
    await service.shutdown()


@pytest.mark.asyncio
async def test_submit_returns_while_agent_is_still_blocked_and_persists_on_success() -> (
    None
):
    control = RunControl(response="private final response")
    agent = ControlledAgent({"private request": control})
    store = InMemoryHistoryStore()
    service = AgentService(agent, store)
    dialog_id = await service.start_dialog()

    await asyncio.wait_for(
        service.submit(dialog_id, UserRequest(content="private request")),
        timeout=0.1,
    )
    await asyncio.wait_for(control.started.wait(), timeout=0.1)

    assert not control.release.is_set()
    assert await store.get(dialog_id) == ()

    control.release.set()
    history = await wait_for_history_size(store, dialog_id, 2)

    assert [(message.role, message.content) for message in history] == [
        (MessageRole.USER, "private request"),
        (MessageRole.ASSISTANT, "private final response"),
    ]
    await service.shutdown()


@pytest.mark.asyncio
async def test_subscription_receives_ordered_events_after_history_is_persisted() -> (
    None
):
    control = RunControl(response="answer")
    store = InMemoryHistoryStore()
    service = AgentService(ControlledAgent({"question": control}), store)
    dialog_id = await service.start_dialog()
    subscription = await service.subscribe(dialog_id)

    await service.submit(dialog_id, UserRequest(content="question"))
    assert await subscription.receive() == DialogEvent(
        type=DialogEventType.MESSAGE_START
    )
    control.release.set()
    assert await subscription.receive() == DialogEvent(
        type=DialogEventType.MESSAGE_DELTA,
        delta="answer",
    )
    assert await subscription.receive() == DialogEvent(type=DialogEventType.MESSAGE_END)
    assert len(await store.get(dialog_id)) == 2

    await service.unsubscribe(subscription)
    await service.shutdown()


@pytest.mark.asyncio
async def test_events_are_broadcast_to_all_active_subscribers() -> None:
    control = RunControl(response="answer")
    service = AgentService(
        ControlledAgent({"question": control}), InMemoryHistoryStore()
    )
    dialog_id = await service.start_dialog()
    first = await service.subscribe(dialog_id)
    second = await service.subscribe(dialog_id)

    await service.submit(dialog_id, UserRequest(content="question"))
    control.release.set()

    expected = [
        DialogEvent(type=DialogEventType.MESSAGE_START),
        DialogEvent(type=DialogEventType.MESSAGE_DELTA, delta="answer"),
        DialogEvent(type=DialogEventType.MESSAGE_END),
    ]
    assert [await first.receive() for _ in expected] == expected
    assert [await second.receive() for _ in expected] == expected

    await service.shutdown()


@pytest.mark.asyncio
async def test_slow_subscriber_is_closed_without_blocking_agent() -> None:
    control = RunControl(response="answer")
    store = InMemoryHistoryStore()
    service = AgentService(
        ControlledAgent({"question": control}),
        store,
        subscriber_queue_size=1,
    )
    dialog_id = await service.start_dialog()
    subscription = await service.subscribe(dialog_id)

    await service.submit(dialog_id, UserRequest(content="question"))
    control.release.set()
    await wait_for_history_size(store, dialog_id, 2)

    assert subscription.closed
    await service.shutdown()


@pytest.mark.asyncio
async def test_failure_after_delta_emits_safe_error_and_keeps_history_empty() -> None:
    store = InMemoryHistoryStore()
    service = AgentService(PartiallyFailingAgent(), store)
    dialog_id = await service.start_dialog()
    subscription = await service.subscribe(dialog_id)

    await service.submit(dialog_id, UserRequest(content="private request"))

    assert await subscription.receive() == DialogEvent(
        type=DialogEventType.MESSAGE_START
    )
    assert await subscription.receive() == DialogEvent(
        type=DialogEventType.MESSAGE_DELTA,
        delta="private partial response",
    )
    assert await subscription.receive() == DialogEvent(
        type=DialogEventType.MESSAGE_ERROR,
        code="agent_error",
        message="Agent request failed.",
    )
    assert await store.get(dialog_id) == ()
    await service.shutdown()


@pytest.mark.asyncio
async def test_late_subscription_does_not_replay_completed_events() -> None:
    control = RunControl(response="answer")
    store = InMemoryHistoryStore()
    service = AgentService(ControlledAgent({"question": control}), store)
    dialog_id = await service.start_dialog()

    await service.submit(dialog_id, UserRequest(content="question"))
    control.release.set()
    await wait_for_history_size(store, dialog_id, 2)
    subscription = await service.subscribe(dialog_id)
    await service.shutdown()

    assert await subscription.receive() is None


@pytest.mark.asyncio
async def test_requests_for_one_dialog_run_in_order_with_completed_history() -> None:
    first = RunControl(response="first answer")
    second = RunControl(response="second answer")
    agent = ControlledAgent({"first": first, "second": second})
    store = InMemoryHistoryStore()
    service = AgentService(agent, store)
    dialog_id = await service.start_dialog()

    await service.submit(dialog_id, UserRequest(content="first"))
    await service.submit(dialog_id, UserRequest(content="second"))
    await asyncio.wait_for(first.started.wait(), timeout=0.1)
    await asyncio.sleep(0)

    assert not second.started.is_set()

    first.release.set()
    await asyncio.wait_for(second.started.wait(), timeout=0.1)

    second_history, second_request = agent.calls[1]
    assert second_request.content == "second"
    assert [(message.role, message.content) for message in second_history] == [
        (MessageRole.USER, "first"),
        (MessageRole.ASSISTANT, "first answer"),
    ]

    second.release.set()
    await wait_for_history_size(store, dialog_id, 4)
    await service.shutdown()


@pytest.mark.asyncio
async def test_different_dialogs_run_independently() -> None:
    first = RunControl()
    second = RunControl()
    agent = ControlledAgent({"first": first, "second": second})
    store = InMemoryHistoryStore()
    service = AgentService(agent, store)
    first_dialog_id = await service.start_dialog()
    second_dialog_id = await service.start_dialog()

    await service.submit(first_dialog_id, UserRequest(content="first"))
    await service.submit(second_dialog_id, UserRequest(content="second"))

    await asyncio.wait_for(first.started.wait(), timeout=0.1)
    await asyncio.wait_for(second.started.wait(), timeout=0.1)
    first.release.set()
    second.release.set()
    await wait_for_history_size(store, first_dialog_id, 2)
    await wait_for_history_size(store, second_dialog_id, 2)
    await service.shutdown()


@pytest.mark.asyncio
async def test_unknown_dialog_is_rejected_before_agent_task_is_created() -> None:
    agent = ControlledAgent({})
    service = AgentService(agent, InMemoryHistoryStore())
    missing_dialog_id = uuid4()

    with pytest.raises(DialogNotFoundError):
        await service.submit(missing_dialog_id, UserRequest(content="request"))

    assert agent.calls == []
    await service.shutdown()


@pytest.mark.asyncio
async def test_agent_failure_does_not_change_history(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.application.agent_service")
    control = RunControl(error=RuntimeError("private failure detail"))
    agent = ControlledAgent({"private request": control})
    store = InMemoryHistoryStore()
    service = AgentService(agent, store)
    dialog_id = await service.start_dialog()

    await service.submit(dialog_id, UserRequest(content="private request"))
    await asyncio.wait_for(control.started.wait(), timeout=0.1)
    control.release.set()

    async def wait_for_failure_log() -> None:
        while not any(
            record.getMessage().startswith("dialog.run.failed ")
            for record in caplog.records
        ):
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_failure_log(), timeout=1)

    assert await store.get(dialog_id) == ()
    assert "private request" not in caplog.text
    assert "private failure detail" not in caplog.text
    failure_record = next(
        record
        for record in caplog.records
        if record.getMessage().startswith("dialog.run.failed ")
    )
    assert failure_record.dialog_id == str(dialog_id)
    assert failure_record.error_type == "RuntimeError"
    await service.shutdown()


@pytest.mark.asyncio
async def test_shutdown_cancels_tasks_and_rejects_new_submissions() -> None:
    control = RunControl()
    agent = ControlledAgent({"request": control})
    store = InMemoryHistoryStore()
    service = AgentService(agent, store)
    dialog_id = await service.start_dialog()
    await service.submit(dialog_id, UserRequest(content="request"))
    await asyncio.wait_for(control.started.wait(), timeout=0.1)

    await asyncio.wait_for(service.shutdown(), timeout=0.1)

    assert control.cancelled.is_set()
    assert await store.get(dialog_id) == ()
    with pytest.raises(AgentServiceUnavailableError):
        await service.submit(dialog_id, UserRequest(content="request"))


@pytest.mark.asyncio
async def test_service_logs_lifecycle_without_message_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.application.agent_service")
    control = RunControl(response="private response")
    store = InMemoryHistoryStore()
    service = AgentService(ControlledAgent({"private request": control}), store)
    dialog_id = await service.start_dialog()

    await service.submit(dialog_id, UserRequest(content="private request"))
    await asyncio.wait_for(control.started.wait(), timeout=0.1)
    control.release.set()
    await wait_for_history_size(store, dialog_id, 2)

    events = [record.getMessage().split()[0] for record in caplog.records]
    assert events == [
        "dialog.created",
        "dialog.request.accepted",
        "dialog.run.started",
        "dialog.run.completed",
        "dialog.history.persisted",
    ]
    assert all(record.dialog_id == str(dialog_id) for record in caplog.records)
    assert all(
        f"dialog_id={dialog_id}" in record.getMessage() for record in caplog.records
    )
    assert "private request" not in caplog.text
    assert "private response" not in caplog.text
    await service.shutdown()
