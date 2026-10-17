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
    DialogEventBroker,
    DialogEventType,
    DialogSubscription,
    InMemoryDialogEventBroker,
)
from smeshariki_ai.dialogs import (
    DialogNotFoundError,
    DialogStoreUnavailableError,
    DialogSummary,
    DialogTranscript,
    InMemoryHistoryStore,
    MessageNotFoundError,
)
from smeshariki_ai.observability import bind_context

OWNER = UUID(int=1)
STRANGER = UUID(int=2)


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


class RecordingSubscription:
    def __init__(self, dialog_id: UUID) -> None:
        self.dialog_id = dialog_id
        self.closed = False

    async def receive(self) -> DialogEvent | None:
        return None


class RecordingBroker(DialogEventBroker):
    def __init__(self, cancelled: asyncio.Event | None = None) -> None:
        self.cancelled = cancelled
        self.subscribed: list[UUID] = []
        self.unsubscribed: list[DialogSubscription] = []
        self.published: list[tuple[UUID, DialogEvent]] = []
        self.shutdown_called = False
        self.shutdown_after_cancellation: bool | None = None

    async def subscribe(self, dialog_id: UUID) -> DialogSubscription:
        self.subscribed.append(dialog_id)
        return RecordingSubscription(dialog_id)

    async def unsubscribe(self, subscription: DialogSubscription) -> None:
        self.unsubscribed.append(subscription)

    async def publish(self, dialog_id: UUID, event: DialogEvent) -> None:
        self.published.append((dialog_id, event))

    async def shutdown(self) -> None:
        self.shutdown_called = True
        if self.cancelled is not None:
            self.shutdown_after_cancellation = self.cancelled.is_set()


def make_service(
    agent: object,
    history_store: InMemoryHistoryStore,
    *,
    broker: DialogEventBroker | None = None,
    queue_size: int = 64,
) -> AgentService:
    event_broker = broker or InMemoryDialogEventBroker(queue_size=queue_size)
    return AgentService(agent, history_store, event_broker)  # type: ignore[arg-type]


async def wait_for_history_size(
    store: InMemoryHistoryStore,
    dialog_id: UUID,
    expected_size: int,
) -> tuple[Message, ...]:
    async def wait() -> tuple[Message, ...]:
        while True:
            history = await store.get(OWNER, dialog_id)
            if len(history) == expected_size:
                return history
            await asyncio.sleep(0)

    return await asyncio.wait_for(wait(), timeout=1)


@pytest.mark.asyncio
async def test_start_dialog_delegates_to_history_store() -> None:
    store = InMemoryHistoryStore()
    service = make_service(ControlledAgent({}), store)

    dialog_id = await service.start_dialog(OWNER)

    assert dialog_id.version == 4
    assert await store.get(OWNER, dialog_id) == ()
    await service.shutdown()


@pytest.mark.asyncio
async def test_subscription_and_events_are_delegated_to_broker() -> None:
    control = RunControl(response="answer")
    broker = RecordingBroker()
    store = InMemoryHistoryStore()
    service = make_service(
        ControlledAgent({"question": control}),
        store,
        broker=broker,
    )
    dialog_id = await service.start_dialog(OWNER)

    subscription = await service.subscribe(OWNER, dialog_id)
    await service.submit(OWNER, dialog_id, UserRequest(content="question"))
    await asyncio.wait_for(control.started.wait(), timeout=0.1)
    control.release.set()
    await wait_for_history_size(store, dialog_id, 2)
    await service.unsubscribe(subscription)
    await service.shutdown()

    assert broker.subscribed == [dialog_id]
    assert broker.unsubscribed == [subscription]
    assert broker.published == [
        (dialog_id, DialogEvent(type=DialogEventType.MESSAGE_START)),
        (
            dialog_id,
            DialogEvent(type=DialogEventType.MESSAGE_DELTA, delta="answer"),
        ),
        (dialog_id, DialogEvent(type=DialogEventType.MESSAGE_END, message_id=2)),
    ]
    assert broker.shutdown_called


@pytest.mark.asyncio
async def test_unknown_dialog_is_rejected_before_broker_subscription() -> None:
    broker = RecordingBroker()
    service = make_service(
        ControlledAgent({}),
        InMemoryHistoryStore(),
        broker=broker,
    )

    with pytest.raises(DialogNotFoundError):
        await service.subscribe(OWNER, uuid4())

    assert broker.subscribed == []
    await service.shutdown()


@pytest.mark.asyncio
async def test_submit_returns_while_agent_is_still_blocked_and_persists_on_success() -> (
    None
):
    control = RunControl(response="private final response")
    agent = ControlledAgent({"private request": control})
    store = InMemoryHistoryStore()
    service = make_service(agent, store)
    dialog_id = await service.start_dialog(OWNER)

    await asyncio.wait_for(
        service.submit(OWNER, dialog_id, UserRequest(content="private request")),
        timeout=0.1,
    )
    await asyncio.wait_for(control.started.wait(), timeout=0.1)

    assert not control.release.is_set()
    assert await store.get(OWNER, dialog_id) == ()

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
    service = make_service(ControlledAgent({"question": control}), store)
    dialog_id = await service.start_dialog(OWNER)
    subscription = await service.subscribe(OWNER, dialog_id)

    await service.submit(OWNER, dialog_id, UserRequest(content="question"))
    assert await subscription.receive() == DialogEvent(
        type=DialogEventType.MESSAGE_START
    )
    control.release.set()
    assert await subscription.receive() == DialogEvent(
        type=DialogEventType.MESSAGE_DELTA,
        delta="answer",
    )
    assert await subscription.receive() == DialogEvent(
        type=DialogEventType.MESSAGE_END, message_id=2
    )
    assert len(await store.get(OWNER, dialog_id)) == 2

    await service.unsubscribe(subscription)
    await service.shutdown()


@pytest.mark.asyncio
async def test_events_are_broadcast_to_all_active_subscribers() -> None:
    control = RunControl(response="answer")
    service = make_service(
        ControlledAgent({"question": control}), InMemoryHistoryStore()
    )
    dialog_id = await service.start_dialog(OWNER)
    first = await service.subscribe(OWNER, dialog_id)
    second = await service.subscribe(OWNER, dialog_id)

    await service.submit(OWNER, dialog_id, UserRequest(content="question"))
    control.release.set()

    expected = [
        DialogEvent(type=DialogEventType.MESSAGE_START),
        DialogEvent(type=DialogEventType.MESSAGE_DELTA, delta="answer"),
        DialogEvent(type=DialogEventType.MESSAGE_END, message_id=2),
    ]
    assert [await first.receive() for _ in expected] == expected
    assert [await second.receive() for _ in expected] == expected

    await service.shutdown()


@pytest.mark.asyncio
async def test_slow_subscriber_is_closed_without_blocking_agent() -> None:
    control = RunControl(response="answer")
    store = InMemoryHistoryStore()
    service = make_service(
        ControlledAgent({"question": control}),
        store,
        queue_size=1,
    )
    dialog_id = await service.start_dialog(OWNER)
    subscription = await service.subscribe(OWNER, dialog_id)

    await service.submit(OWNER, dialog_id, UserRequest(content="question"))
    control.release.set()
    await wait_for_history_size(store, dialog_id, 2)

    assert subscription.closed
    await service.shutdown()


@pytest.mark.asyncio
async def test_failure_after_delta_emits_safe_error_and_keeps_history_empty() -> None:
    store = InMemoryHistoryStore()
    service = make_service(PartiallyFailingAgent(), store)
    dialog_id = await service.start_dialog(OWNER)
    subscription = await service.subscribe(OWNER, dialog_id)

    await service.submit(OWNER, dialog_id, UserRequest(content="private request"))

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
    assert await store.get(OWNER, dialog_id) == ()
    await service.shutdown()


@pytest.mark.asyncio
async def test_late_subscription_does_not_replay_completed_events() -> None:
    control = RunControl(response="answer")
    store = InMemoryHistoryStore()
    service = make_service(ControlledAgent({"question": control}), store)
    dialog_id = await service.start_dialog(OWNER)

    await service.submit(OWNER, dialog_id, UserRequest(content="question"))
    control.release.set()
    await wait_for_history_size(store, dialog_id, 2)
    subscription = await service.subscribe(OWNER, dialog_id)
    await service.shutdown()

    assert await subscription.receive() is None


@pytest.mark.asyncio
async def test_requests_for_one_dialog_run_in_order_with_completed_history(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.application.agent_service")
    first = RunControl(response="first answer")
    second = RunControl(response="second answer")
    agent = ControlledAgent({"first": first, "second": second})
    store = InMemoryHistoryStore()
    service = make_service(agent, store)
    dialog_id = await service.start_dialog(OWNER)

    with bind_context(request_id="request-first"):
        await service.submit(OWNER, dialog_id, UserRequest(content="first"))
    with bind_context(request_id="request-second"):
        await service.submit(OWNER, dialog_id, UserRequest(content="second"))
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
    completed = [
        record.request_id
        for record in caplog.records
        if record.getMessage().startswith("dialog.run.completed")
    ]
    assert completed == ["request-first", "request-second"]
    await service.shutdown()


@pytest.mark.asyncio
async def test_different_dialogs_run_independently(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.application.agent_service")
    first = RunControl()
    second = RunControl()
    agent = ControlledAgent({"first": first, "second": second})
    store = InMemoryHistoryStore()
    service = make_service(agent, store)
    first_dialog_id = await service.start_dialog(OWNER)
    second_dialog_id = await service.start_dialog(OWNER)

    with bind_context(request_id="request-first"):
        await service.submit(OWNER, first_dialog_id, UserRequest(content="first"))
    with bind_context(request_id="request-second"):
        await service.submit(OWNER, second_dialog_id, UserRequest(content="second"))

    await asyncio.wait_for(first.started.wait(), timeout=0.1)
    await asyncio.wait_for(second.started.wait(), timeout=0.1)
    first.release.set()
    second.release.set()
    await wait_for_history_size(store, first_dialog_id, 2)
    await wait_for_history_size(store, second_dialog_id, 2)
    completed = {
        record.dialog_id: record.request_id
        for record in caplog.records
        if record.getMessage().startswith("dialog.run.completed")
    }
    assert completed == {
        str(first_dialog_id): "request-first",
        str(second_dialog_id): "request-second",
    }
    await service.shutdown()


@pytest.mark.asyncio
async def test_unknown_dialog_is_rejected_before_agent_task_is_created() -> None:
    agent = ControlledAgent({})
    service = make_service(agent, InMemoryHistoryStore())
    missing_dialog_id = uuid4()

    with pytest.raises(DialogNotFoundError):
        await service.submit(OWNER, missing_dialog_id, UserRequest(content="request"))

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
    service = make_service(agent, store)
    dialog_id = await service.start_dialog(OWNER)

    await service.submit(OWNER, dialog_id, UserRequest(content="private request"))
    await asyncio.wait_for(control.started.wait(), timeout=0.1)
    control.release.set()

    async def wait_for_failure_log() -> None:
        while not any(
            record.getMessage().startswith("dialog.run.failed ")
            for record in caplog.records
        ):
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_failure_log(), timeout=1)

    assert await store.get(OWNER, dialog_id) == ()
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
    broker = RecordingBroker(control.cancelled)
    service = make_service(agent, store, broker=broker)
    dialog_id = await service.start_dialog(OWNER)
    await service.submit(OWNER, dialog_id, UserRequest(content="request"))
    await asyncio.wait_for(control.started.wait(), timeout=0.1)

    await asyncio.wait_for(service.shutdown(), timeout=0.1)

    assert control.cancelled.is_set()
    assert broker.shutdown_after_cancellation is True
    assert await store.get(OWNER, dialog_id) == ()
    with pytest.raises(AgentServiceUnavailableError):
        await service.submit(OWNER, dialog_id, UserRequest(content="request"))


@pytest.mark.asyncio
async def test_service_logs_lifecycle_without_message_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.application.agent_service")
    control = RunControl(response="private response")
    store = InMemoryHistoryStore()
    service = make_service(ControlledAgent({"private request": control}), store)
    dialog_id = await service.start_dialog(OWNER)

    with bind_context(request_id="request-1"):
        await service.submit(OWNER, dialog_id, UserRequest(content="private request"))
    await asyncio.wait_for(control.started.wait(), timeout=0.1)
    control.release.set()
    await wait_for_history_size(store, dialog_id, 2)

    events = [record.getMessage().split()[0] for record in caplog.records]
    assert events == [
        "dialog.created",
        "dialog.request.accepted",
        "dialog.run.started",
        "dialog.history.persisted",
        "dialog.run.completed",
    ]
    assert all(record.dialog_id == str(dialog_id) for record in caplog.records)
    assert all(
        f"dialog_id={dialog_id}" in record.getMessage() for record in caplog.records
    )
    assert "private request" not in caplog.text
    assert "private response" not in caplog.text
    run_completion = next(
        record
        for record in caplog.records
        if record.getMessage().startswith("dialog.run.completed ")
    )
    assert run_completion.request_id == "request-1"
    assert run_completion.started_at.endswith("Z")
    assert run_completion.duration_ms >= 0
    assert run_completion.outcome == "completed"
    await service.shutdown()


class UnavailableHistoryStore(InMemoryHistoryStore):
    async def create(self, owner_id: UUID) -> UUID:
        raise DialogStoreUnavailableError

    async def list_dialogs(
        self, owner_id: UUID, *, limit: int
    ) -> tuple[DialogSummary, ...]:
        raise DialogStoreUnavailableError

    async def transcript(self, owner_id: UUID, dialog_id: UUID) -> DialogTranscript:
        raise DialogStoreUnavailableError


@pytest.mark.asyncio
async def test_foreign_dialog_is_not_found_for_submit_and_subscribe() -> None:
    store = InMemoryHistoryStore()
    agent = ControlledAgent({})
    broker = RecordingBroker()
    service = make_service(agent, store, broker=broker)
    dialog_id = await service.start_dialog(OWNER)

    with pytest.raises(DialogNotFoundError):
        await service.submit(STRANGER, dialog_id, UserRequest(content="request"))
    with pytest.raises(DialogNotFoundError):
        await service.subscribe(STRANGER, dialog_id)
    with pytest.raises(DialogNotFoundError):
        await service.transcript(STRANGER, dialog_id)

    assert agent.calls == []
    assert broker.subscribed == []
    await service.shutdown()


@pytest.mark.asyncio
async def test_completed_run_is_listed_with_title_and_transcript() -> None:
    control = RunControl(response="Однажды…")
    store = InMemoryHistoryStore()
    service = make_service(ControlledAgent({"Крош строит ракету": control}), store)
    dialog_id = await service.start_dialog(OWNER)
    await service.start_dialog(OWNER)

    await service.submit(OWNER, dialog_id, UserRequest(content="Крош строит ракету"))
    control.release.set()
    await wait_for_history_size(store, dialog_id, 2)

    dialogs = await service.list_dialogs(OWNER)
    transcript = await service.transcript(OWNER, dialog_id)
    assert [(item.dialog_id, item.title) for item in dialogs] == [
        (dialog_id, "Крош строит ракету")
    ]
    assert await service.list_dialogs(STRANGER) == ()
    assert transcript.title == "Крош строит ракету"
    assert [(item.role, item.content) for item in transcript.messages] == [
        (MessageRole.USER, "Крош строит ракету"),
        (MessageRole.ASSISTANT, "Однажды…"),
    ]
    await service.shutdown()


@pytest.mark.asyncio
async def test_list_is_limited_to_fifty_dialogs() -> None:
    store = InMemoryHistoryStore()
    service = make_service(ControlledAgent({}), store)
    for _ in range(51):
        dialog_id = await service.start_dialog(OWNER)
        await store.append(
            dialog_id, (Message(role=MessageRole.USER, content="story"),)
        )

    assert len(await service.list_dialogs(OWNER)) == 50
    await service.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["start", "list", "transcript"])
async def test_store_failure_is_propagated(operation: str) -> None:
    service = make_service(ControlledAgent({}), UnavailableHistoryStore())

    with pytest.raises(DialogStoreUnavailableError):
        if operation == "start":
            await service.start_dialog(OWNER)
        elif operation == "list":
            await service.list_dialogs(OWNER)
        else:
            await service.transcript(OWNER, uuid4())
    await service.shutdown()


class FailingAppendStore(InMemoryHistoryStore):
    async def append(self, dialog_id: UUID, messages: Sequence[Message]) -> None:
        raise DialogStoreUnavailableError


@pytest.mark.asyncio
async def test_failed_save_publishes_error_and_keeps_history() -> None:
    control = RunControl(response="answer")
    store = FailingAppendStore()
    broker = RecordingBroker()
    service = make_service(ControlledAgent({"question": control}), store, broker=broker)
    dialog_id = await service.start_dialog(OWNER)

    await service.submit(OWNER, dialog_id, UserRequest(content="question"))
    control.release.set()

    async def wait_for_error() -> None:
        while not any(
            event.type is DialogEventType.MESSAGE_ERROR for _, event in broker.published
        ):
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_error(), timeout=1)
    assert DialogEventType.MESSAGE_END not in [
        event.type for _, event in broker.published
    ]
    assert await store.get(OWNER, dialog_id) == ()
    await service.shutdown()


@pytest.mark.asyncio
async def test_reading_time_reaches_agent_but_not_history() -> None:
    control = RunControl(response="answer")
    store = InMemoryHistoryStore()
    agent = ControlledAgent({"question": control})
    service = make_service(agent, store)
    dialog_id = await service.start_dialog(OWNER)

    await service.submit(
        OWNER, dialog_id, UserRequest(content="question", reading_minutes=5)
    )
    control.release.set()
    history = await wait_for_history_size(store, dialog_id, 2)

    assert agent.calls[0][1].reading_minutes == 5
    assert history[0] == Message(role=MessageRole.USER, content="question")
    await service.shutdown()


@pytest.mark.asyncio
async def test_message_end_carries_the_saved_answer_id() -> None:
    control = RunControl(response="answer")
    store = InMemoryHistoryStore()
    broker = RecordingBroker()
    service = make_service(ControlledAgent({"question": control}), store, broker=broker)
    dialog_id = await service.start_dialog(OWNER)

    await service.submit(OWNER, dialog_id, UserRequest(content="question"))
    control.release.set()
    await wait_for_history_size(store, dialog_id, 2)

    async def wait_for_end() -> DialogEvent:
        while True:
            for _, event in broker.published:
                if event.type is DialogEventType.MESSAGE_END:
                    return event
            await asyncio.sleep(0)

    end = await asyncio.wait_for(wait_for_end(), timeout=1)
    answer = (await store.transcript(OWNER, dialog_id)).messages[-1]
    assert answer.role is MessageRole.ASSISTANT
    assert end.message_id == answer.id
    await service.shutdown()


@pytest.mark.asyncio
async def test_feedback_is_delegated_and_checked_for_ownership(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.application.agent_service")
    store = InMemoryHistoryStore()
    service = make_service(ControlledAgent({}), store)
    dialog_id = await service.start_dialog(OWNER)
    _, answer_id = await store.append(
        dialog_id,
        (
            Message(role=MessageRole.USER, content="q"),
            Message(role=MessageRole.ASSISTANT, content="a"),
        ),
    )

    await service.set_feedback(OWNER, dialog_id, answer_id, 2)
    assert (await store.transcript(OWNER, dialog_id)).messages[1].feedback == 2
    [record] = [
        record
        for record in caplog.records
        if record.getMessage().startswith("dialog.feedback.set")
    ]
    assert record.log_fields["score"] == 2
    assert "feedback" not in record.log_fields
    await service.clear_feedback(OWNER, dialog_id, answer_id)
    assert (await store.transcript(OWNER, dialog_id)).messages[1].feedback is None
    with pytest.raises(MessageNotFoundError):
        await service.set_feedback(STRANGER, dialog_id, answer_id, 5)
    await service.shutdown()
