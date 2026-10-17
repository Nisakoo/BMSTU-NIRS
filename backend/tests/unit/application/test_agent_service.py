import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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
    DRAFT_TTL,
    DialogDrafts,
    DialogNotFoundError,
    HistoryUnavailableError,
    InMemoryHistoryStore,
)
from smeshariki_ai.observability import bind_context

OWNER_ID = UUID(int=1)
OTHER_ID = UUID(int=2)
NOW_FOR_TESTS = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


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
        self.closed_dialogs: list[UUID] = []
        self.shutdown_called = False
        self.shutdown_after_cancellation: bool | None = None

    async def subscribe(self, dialog_id: UUID) -> DialogSubscription:
        self.subscribed.append(dialog_id)
        return RecordingSubscription(dialog_id)

    async def unsubscribe(self, subscription: DialogSubscription) -> None:
        self.unsubscribed.append(subscription)

    async def publish(self, dialog_id: UUID, event: DialogEvent) -> None:
        self.published.append((dialog_id, event))

    async def close_dialog(self, dialog_id: UUID) -> None:
        self.closed_dialogs.append(dialog_id)

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
            try:
                history = await store.get(dialog_id)
            except DialogNotFoundError:
                # A draft is not stored until its first answer.
                history = ()
            if len(history) == expected_size:
                return history
            await asyncio.sleep(0)

    return await asyncio.wait_for(wait(), timeout=1)


async def assert_not_stored(store: InMemoryHistoryStore, dialog_id: UUID) -> None:
    with pytest.raises(DialogNotFoundError):
        await store.get(dialog_id)


@pytest.mark.asyncio
async def test_start_dialog_creates_a_draft_without_touching_history_store() -> None:
    store = InMemoryHistoryStore()
    service = make_service(ControlledAgent({}), store)

    dialog_id = await service.start_dialog(OWNER_ID)

    assert dialog_id.version == 4
    await assert_not_stored(store, dialog_id)
    assert await store.list(OWNER_ID, 10, None) == ()
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
    dialog_id = await service.start_dialog(OWNER_ID)

    subscription = await service.subscribe(dialog_id, OWNER_ID)
    await service.submit(dialog_id, OWNER_ID, UserRequest(content="question"))
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
        (dialog_id, DialogEvent(type=DialogEventType.MESSAGE_END)),
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
        await service.subscribe(uuid4(), OWNER_ID)

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
    dialog_id = await service.start_dialog(OWNER_ID)

    await asyncio.wait_for(
        service.submit(dialog_id, OWNER_ID, UserRequest(content="private request")),
        timeout=0.1,
    )
    await asyncio.wait_for(control.started.wait(), timeout=0.1)

    assert not control.release.is_set()
    await assert_not_stored(store, dialog_id)

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
    dialog_id = await service.start_dialog(OWNER_ID)
    subscription = await service.subscribe(dialog_id, OWNER_ID)

    await service.submit(dialog_id, OWNER_ID, UserRequest(content="question"))
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
    service = make_service(
        ControlledAgent({"question": control}), InMemoryHistoryStore()
    )
    dialog_id = await service.start_dialog(OWNER_ID)
    first = await service.subscribe(dialog_id, OWNER_ID)
    second = await service.subscribe(dialog_id, OWNER_ID)

    await service.submit(dialog_id, OWNER_ID, UserRequest(content="question"))
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
    service = make_service(
        ControlledAgent({"question": control}),
        store,
        queue_size=1,
    )
    dialog_id = await service.start_dialog(OWNER_ID)
    subscription = await service.subscribe(dialog_id, OWNER_ID)

    await service.submit(dialog_id, OWNER_ID, UserRequest(content="question"))
    control.release.set()
    await wait_for_history_size(store, dialog_id, 2)

    assert subscription.closed
    await service.shutdown()


@pytest.mark.asyncio
async def test_failure_after_delta_emits_safe_error_and_keeps_history_empty() -> None:
    store = InMemoryHistoryStore()
    service = make_service(PartiallyFailingAgent(), store)
    dialog_id = await service.start_dialog(OWNER_ID)
    subscription = await service.subscribe(dialog_id, OWNER_ID)

    await service.submit(dialog_id, OWNER_ID, UserRequest(content="private request"))

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
    await assert_not_stored(store, dialog_id)
    await service.shutdown()


@pytest.mark.asyncio
async def test_late_subscription_does_not_replay_completed_events() -> None:
    control = RunControl(response="answer")
    store = InMemoryHistoryStore()
    service = make_service(ControlledAgent({"question": control}), store)
    dialog_id = await service.start_dialog(OWNER_ID)

    await service.submit(dialog_id, OWNER_ID, UserRequest(content="question"))
    control.release.set()
    await wait_for_history_size(store, dialog_id, 2)
    subscription = await service.subscribe(dialog_id, OWNER_ID)
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
    dialog_id = await service.start_dialog(OWNER_ID)

    with bind_context(request_id="request-first"):
        await service.submit(dialog_id, OWNER_ID, UserRequest(content="first"))
    with bind_context(request_id="request-second"):
        await service.submit(dialog_id, OWNER_ID, UserRequest(content="second"))
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
    first_dialog_id = await service.start_dialog(OWNER_ID)
    second_dialog_id = await service.start_dialog(OWNER_ID)

    with bind_context(request_id="request-first"):
        await service.submit(first_dialog_id, OWNER_ID, UserRequest(content="first"))
    with bind_context(request_id="request-second"):
        await service.submit(second_dialog_id, OWNER_ID, UserRequest(content="second"))

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
        await service.submit(
            missing_dialog_id, OWNER_ID, UserRequest(content="request")
        )

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
    dialog_id = await service.start_dialog(OWNER_ID)

    await service.submit(dialog_id, OWNER_ID, UserRequest(content="private request"))
    await asyncio.wait_for(control.started.wait(), timeout=0.1)
    control.release.set()

    async def wait_for_failure_log() -> None:
        while not any(
            record.getMessage().startswith("dialog.run.failed ")
            for record in caplog.records
        ):
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_failure_log(), timeout=1)

    await assert_not_stored(store, dialog_id)
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
    dialog_id = await service.start_dialog(OWNER_ID)
    await service.submit(dialog_id, OWNER_ID, UserRequest(content="request"))
    await asyncio.wait_for(control.started.wait(), timeout=0.1)

    await asyncio.wait_for(service.shutdown(), timeout=0.1)

    assert control.cancelled.is_set()
    assert broker.shutdown_after_cancellation is True
    await assert_not_stored(store, dialog_id)
    with pytest.raises(AgentServiceUnavailableError):
        await service.submit(dialog_id, OWNER_ID, UserRequest(content="request"))


@pytest.mark.asyncio
async def test_service_logs_lifecycle_without_message_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.application.agent_service")
    control = RunControl(response="private response")
    store = InMemoryHistoryStore()
    service = make_service(ControlledAgent({"private request": control}), store)
    dialog_id = await service.start_dialog(OWNER_ID)

    with bind_context(request_id="request-1"):
        await service.submit(
            dialog_id, OWNER_ID, UserRequest(content="private request")
        )
    await asyncio.wait_for(control.started.wait(), timeout=0.1)
    control.release.set()
    await wait_for_history_size(store, dialog_id, 2)

    events = [record.getMessage().split()[0] for record in caplog.records]
    assert events == [
        "dialog.created",
        "dialog.request.accepted",
        "dialog.run.started",
        "dialog.persisted",
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


@pytest.mark.asyncio
async def test_foreign_dialog_is_rejected_without_task_or_subscription(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.application.agent_service")
    agent = ControlledAgent({})
    broker = RecordingBroker()
    store = InMemoryHistoryStore()
    service = make_service(agent, store, broker=broker)
    dialog_id = await service.start_dialog(OWNER_ID)

    with pytest.raises(DialogNotFoundError):
        await service.submit(
            dialog_id, OTHER_ID, UserRequest(content="private request")
        )
    with pytest.raises(DialogNotFoundError):
        await service.subscribe(dialog_id, OTHER_ID)
    await service.shutdown()

    assert agent.calls == []
    assert broker.subscribed == []
    assert broker.published == []
    await assert_not_stored(store, dialog_id)
    denied = [
        record
        for record in caplog.records
        if record.getMessage().split()[0] == "dialog.access.denied"
    ]
    assert len(denied) == 2
    assert all(
        record.dialog_id == str(dialog_id)
        and record.user_id == str(OTHER_ID)
        and record.outcome == "foreign"
        for record in denied
    )
    assert "private request" not in caplog.text


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


class FailingCreateStore(InMemoryHistoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.failures = 1

    async def create(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if self.failures:
            self.failures -= 1
            raise HistoryUnavailableError
        await super().create(*args, **kwargs)


async def receive_events(subscription: DialogSubscription) -> list[DialogEvent]:
    events: list[DialogEvent] = []
    while (event := await asyncio.wait_for(subscription.receive(), 1)) is not None:
        events.append(event)
    return events


async def run_to_completion(
    service: AgentService, dialog_id: UUID, content: str, control: RunControl
) -> None:
    subscription = await service.subscribe(dialog_id, OWNER_ID)
    await service.submit(dialog_id, OWNER_ID, UserRequest(content=content))
    control.release.set()
    while (event := await subscription.receive()) is not None:
        if event.type in (DialogEventType.MESSAGE_END, DialogEventType.MESSAGE_ERROR):
            break
    await service.unsubscribe(subscription)


@pytest.mark.asyncio
async def test_first_success_persists_draft_with_title_and_clock_time() -> None:
    clock = Clock()
    store = InMemoryHistoryStore()
    control = RunControl(response="answer")
    long_request = "first\nquestion " + "x" * 100
    service = AgentService(
        ControlledAgent({long_request: control}),  # type: ignore[arg-type]
        store,
        InMemoryDialogEventBroker(),
        clock=clock,
    )
    dialog_id = await service.start_dialog(OWNER_ID)
    subscription = await service.subscribe(dialog_id, OWNER_ID)

    await service.submit(dialog_id, OWNER_ID, UserRequest(content=long_request))
    await asyncio.wait_for(control.started.wait(), timeout=0.1)
    assert await store.list(OWNER_ID, 10, None) == ()
    control.release.set()
    events = []
    while not events or events[-1].type is not DialogEventType.MESSAGE_END:
        events.append(await asyncio.wait_for(subscription.receive(), 1))

    # The dialog is stored before message_end is published.
    (summary,) = await store.list(OWNER_ID, 10, None)
    assert summary.dialog_id == dialog_id
    assert summary.title == ("first question " + "x" * 100)[:60] + "…"
    assert summary.created_at == summary.updated_at
    transcript = await service.get_dialog(dialog_id, OWNER_ID)
    assert transcript.title == summary.title
    assert [(m.role, m.content) for m in transcript.messages] == [
        (MessageRole.USER, long_request),
        (MessageRole.ASSISTANT, "answer"),
    ]
    await service.unsubscribe(subscription)
    await service.shutdown()


@pytest.mark.asyncio
async def test_title_is_fixed_by_first_request_and_updated_at_moves() -> None:
    store = InMemoryHistoryStore()
    first = RunControl(response="one")
    second = RunControl(response="two")
    service = make_service(ControlledAgent({"first": first, "second": second}), store)
    dialog_id = await service.start_dialog(OWNER_ID)

    await run_to_completion(service, dialog_id, "first", first)
    (before,) = await store.list(OWNER_ID, 10, None)
    await run_to_completion(service, dialog_id, "second", second)

    (after,) = await store.list(OWNER_ID, 10, None)
    assert after.title == before.title == "first"
    assert after.created_at == before.created_at
    assert after.updated_at > before.updated_at
    assert len(await store.get(dialog_id)) == 4
    await service.shutdown()


@pytest.mark.asyncio
async def test_failed_first_run_keeps_draft_and_next_run_is_first_again() -> None:
    store = InMemoryHistoryStore()
    failing = RunControl(error=RuntimeError("private failure detail"))
    retry = RunControl(response="answer")
    agent = ControlledAgent({"first": failing, "retry": retry})
    service = make_service(agent, store)
    dialog_id = await service.start_dialog(OWNER_ID)

    await run_to_completion(service, dialog_id, "first", failing)
    await assert_not_stored(store, dialog_id)
    await run_to_completion(service, dialog_id, "retry", retry)

    assert agent.calls[1][0] == ()
    (summary,) = await store.list(OWNER_ID, 10, None)
    assert (summary.dialog_id, summary.title) == (dialog_id, "retry")
    assert len(await store.get(dialog_id)) == 2
    await service.shutdown()


@pytest.mark.asyncio
async def test_storage_failure_on_first_save_keeps_draft_and_reports_error() -> None:
    store = FailingCreateStore()
    control = RunControl(response="answer")
    other = RunControl(response="answer")
    service = make_service(ControlledAgent({"first": control, "again": other}), store)
    dialog_id = await service.start_dialog(OWNER_ID)
    subscription = await service.subscribe(dialog_id, OWNER_ID)

    await service.submit(dialog_id, OWNER_ID, UserRequest(content="first"))
    control.release.set()
    types = []
    while DialogEventType.MESSAGE_ERROR not in types:
        event = await asyncio.wait_for(subscription.receive(), 1)
        assert event is not None
        types.append(event.type)

    assert DialogEventType.MESSAGE_END not in types
    await assert_not_stored(store, dialog_id)
    assert (await service.get_dialog(dialog_id, OWNER_ID)).title is None
    await service.unsubscribe(subscription)
    await run_to_completion(service, dialog_id, "again", other)
    assert len(await store.get(dialog_id)) == 2
    await service.shutdown()


@pytest.mark.asyncio
async def test_saved_dialog_survives_service_restart_and_gives_agent_context() -> None:
    store = InMemoryHistoryStore()
    first = RunControl(response="first answer")
    service = make_service(ControlledAgent({"first": first}), store)
    dialog_id = await service.start_dialog(OWNER_ID)
    await run_to_completion(service, dialog_id, "first", first)
    await service.shutdown()

    second = RunControl(response="second answer")
    agent = ControlledAgent({"second": second})
    restarted = make_service(agent, store)
    await run_to_completion(restarted, dialog_id, "second", second)

    assert [(m.role, m.content) for m in agent.calls[0][0]] == [
        (MessageRole.USER, "first"),
        (MessageRole.ASSISTANT, "first answer"),
    ]
    assert len(await store.get(dialog_id)) == 4
    await restarted.shutdown()


@pytest.mark.asyncio
async def test_list_dialogs_pages_only_saved_dialogs_of_the_user() -> None:
    store = InMemoryHistoryStore()
    clock = Clock()
    service = AgentService(
        ControlledAgent({}),  # type: ignore[arg-type]
        store,
        InMemoryDialogEventBroker(),
        clock=clock,
    )
    saved = []
    for index in range(25):
        dialog_id = uuid4()
        await store.create(dialog_id, OWNER_ID, str(index), (), clock())
        saved.append(dialog_id)
    await store.create(uuid4(), OTHER_ID, "foreign", (), clock())
    for _ in range(3):
        await service.start_dialog(OWNER_ID)

    first = await service.list_dialogs(OWNER_ID, 20)
    assert first.next_cursor is not None
    second = await service.list_dialogs(OWNER_ID, 20, first.next_cursor)

    assert [item.dialog_id for item in first.items] == saved[::-1][:20]
    assert [item.dialog_id for item in second.items] == saved[::-1][20:]
    assert second.next_cursor is None
    await service.shutdown()


@pytest.mark.asyncio
async def test_list_dialogs_exact_page_has_no_next_cursor() -> None:
    store = InMemoryHistoryStore()
    service = make_service(ControlledAgent({}), store)
    for index in range(2):
        await store.create(uuid4(), OWNER_ID, str(index), (), NOW_FOR_TESTS)

    page = await service.list_dialogs(OWNER_ID, 2)

    assert len(page.items) == 2
    assert page.next_cursor is None
    await service.shutdown()


@pytest.mark.asyncio
async def test_get_dialog_of_draft_is_empty_and_foreign_access_is_hidden(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.application.agent_service")
    store = InMemoryHistoryStore()
    control = RunControl(response="answer")
    service = make_service(ControlledAgent({"question": control}), store)
    draft_id = await service.start_dialog(OWNER_ID)
    saved_id = await service.start_dialog(OWNER_ID)
    await run_to_completion(service, saved_id, "question", control)

    transcript = await service.get_dialog(draft_id, OWNER_ID)
    assert (transcript.title, transcript.messages) == (None, ())
    for dialog_id in (draft_id, saved_id, uuid4()):
        with pytest.raises(DialogNotFoundError):
            await service.get_dialog(dialog_id, OTHER_ID)
        with pytest.raises(DialogNotFoundError):
            await service.delete_dialog(dialog_id, OTHER_ID)

    assert len(await store.get(saved_id)) == 2
    assert (await service.get_dialog(draft_id, OWNER_ID)).messages == ()
    denied = [
        record
        for record in caplog.records
        if record.getMessage().startswith("dialog.access.denied ")
    ]
    assert len(denied) == 4
    assert {record.user_id for record in denied} == {str(OTHER_ID)}
    await service.shutdown()


@pytest.mark.asyncio
async def test_delete_draft_cancels_runs_and_stores_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="smeshariki_ai.application.agent_service")
    store = InMemoryHistoryStore()
    running = RunControl(response="private answer")
    queued = RunControl(response="private queued")
    unrelated = RunControl(response="other answer")
    agent = ControlledAgent(
        {"running": running, "queued": queued, "unrelated": unrelated}
    )
    broker = InMemoryDialogEventBroker()
    service = AgentService(agent, store, broker)  # type: ignore[arg-type]
    dialog_id = await service.start_dialog(OWNER_ID)
    other_id = await service.start_dialog(OWNER_ID)
    subscription = await service.subscribe(dialog_id, OWNER_ID)
    await service.submit(dialog_id, OWNER_ID, UserRequest(content="running"))
    await service.submit(dialog_id, OWNER_ID, UserRequest(content="queued"))
    await service.submit(other_id, OWNER_ID, UserRequest(content="unrelated"))
    await asyncio.wait_for(running.started.wait(), timeout=0.1)
    await asyncio.wait_for(unrelated.started.wait(), timeout=0.1)

    await service.delete_dialog(dialog_id, OWNER_ID)

    events = await receive_events(subscription)
    assert DialogEventType.MESSAGE_ERROR in [event.type for event in events]
    assert DialogEventType.MESSAGE_END not in [event.type for event in events]
    assert running.cancelled.is_set()
    assert not queued.started.is_set()
    await assert_not_stored(store, dialog_id)
    for call in (
        service.get_dialog(dialog_id, OWNER_ID),
        service.delete_dialog(dialog_id, OWNER_ID),
        service.submit(dialog_id, OWNER_ID, UserRequest(content="running")),
        service.subscribe(dialog_id, OWNER_ID),
    ):
        with pytest.raises(DialogNotFoundError):
            await call
    unrelated.release.set()
    await wait_for_history_size(store, other_id, 2)
    deleted = next(
        record
        for record in caplog.records
        if record.getMessage().startswith("dialog.deleted ")
    )
    assert (deleted.dialog_id, deleted.user_id, deleted.draft) == (
        str(dialog_id),
        str(OWNER_ID),
        True,
    )
    assert "private" not in caplog.text
    await service.shutdown()


@pytest.mark.asyncio
async def test_delete_saved_dialog_removes_rows_and_cancels_runs() -> None:
    store = InMemoryHistoryStore()
    first = RunControl(response="first answer")
    running = RunControl(response="never saved")
    queued = RunControl()
    broker = RecordingBroker()
    service = make_service(
        ControlledAgent({"first": first, "running": running, "queued": queued}),
        store,
        broker=broker,
    )
    dialog_id = await service.start_dialog(OWNER_ID)
    await run_to_completion(service, dialog_id, "first", first)
    await service.submit(dialog_id, OWNER_ID, UserRequest(content="running"))
    await service.submit(dialog_id, OWNER_ID, UserRequest(content="queued"))
    await asyncio.wait_for(running.started.wait(), timeout=0.1)

    await service.delete_dialog(dialog_id, OWNER_ID)

    assert running.cancelled.is_set()
    assert not queued.started.is_set()
    assert broker.closed_dialogs == [dialog_id]
    assert (
        dialog_id,
        DialogEvent(
            type=DialogEventType.MESSAGE_ERROR,
            code="agent_error",
            message="Agent request failed.",
        ),
    ) in broker.published
    with pytest.raises(DialogNotFoundError):
        await store.get(dialog_id)
    assert await store.list(OWNER_ID, 10, None) == ()
    await service.shutdown()


@pytest.mark.asyncio
async def test_delete_before_run_starts_still_reports_error_to_subscribers() -> None:
    store = InMemoryHistoryStore()
    control = RunControl(response="answer")
    service = make_service(ControlledAgent({"question": control}), store)
    dialog_id = await service.start_dialog(OWNER_ID)
    subscription = await service.subscribe(dialog_id, OWNER_ID)
    await service.submit(dialog_id, OWNER_ID, UserRequest(content="question"))

    # The task is cancelled before it has taken its first step.
    await service.delete_dialog(dialog_id, OWNER_ID)

    events = await receive_events(subscription)
    assert [event.type for event in events] == [DialogEventType.MESSAGE_ERROR]
    assert not control.started.is_set()
    await assert_not_stored(store, dialog_id)
    await service.shutdown()


@pytest.mark.asyncio
async def test_delete_after_first_save_committed_removes_the_stored_dialog() -> None:
    saved = asyncio.Event()

    class SlowAfterCreateStore(InMemoryHistoryStore):
        async def create(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            await super().create(*args, **kwargs)
            saved.set()
            # Cancellation lands after the commit, before the draft is discarded.
            await asyncio.Event().wait()

    store = SlowAfterCreateStore()
    control = RunControl(response="answer")
    service = make_service(ControlledAgent({"question": control}), store)
    dialog_id = await service.start_dialog(OWNER_ID)
    await service.submit(dialog_id, OWNER_ID, UserRequest(content="question"))
    control.release.set()
    await asyncio.wait_for(saved.wait(), timeout=1)

    await service.delete_dialog(dialog_id, OWNER_ID)

    await assert_not_stored(store, dialog_id)
    assert await store.list(OWNER_ID, 10, None) == ()
    await service.shutdown()


@pytest.mark.asyncio
async def test_delete_closes_subscriptions_of_the_dialog_only() -> None:
    store = InMemoryHistoryStore()
    service = make_service(ControlledAgent({}), store)
    dialog_id = await service.start_dialog(OWNER_ID)
    other_id = await service.start_dialog(OWNER_ID)
    subscription = await service.subscribe(dialog_id, OWNER_ID)
    other = await service.subscribe(other_id, OWNER_ID)

    await service.delete_dialog(dialog_id, OWNER_ID)

    assert await subscription.receive() is None
    assert not other.closed
    await service.shutdown()


@pytest.mark.asyncio
async def test_storage_failure_on_delete_is_reported_and_dialog_is_kept() -> None:
    class FailingDeleteStore(InMemoryHistoryStore):
        async def delete(self, dialog_id: UUID) -> None:
            raise HistoryUnavailableError

    store = FailingDeleteStore()
    dialog_id = uuid4()
    await store.create(dialog_id, OWNER_ID, "title", (), NOW_FOR_TESTS)
    service = make_service(ControlledAgent({}), store)

    with pytest.raises(HistoryUnavailableError):
        await service.delete_dialog(dialog_id, OWNER_ID)

    assert await store.owner(dialog_id) == OWNER_ID
    # The dialog is not stuck in the deleting state.
    assert (await service.get_dialog(dialog_id, OWNER_ID)).title == "title"
    await service.shutdown()


@pytest.mark.asyncio
async def test_idle_draft_expires_but_subscription_or_run_keeps_it() -> None:
    now = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

    def clock() -> datetime:
        return now

    store = InMemoryHistoryStore()
    control = RunControl(response="answer")
    service = AgentService(
        ControlledAgent({"question": control}),  # type: ignore[arg-type]
        store,
        InMemoryDialogEventBroker(),
        drafts=DialogDrafts(clock=clock),
        clock=clock,
    )
    idle_id = await service.start_dialog(OWNER_ID)
    watched_id = await service.start_dialog(OWNER_ID)
    running_id = await service.start_dialog(OWNER_ID)
    subscription = await service.subscribe(watched_id, OWNER_ID)
    await service.submit(running_id, OWNER_ID, UserRequest(content="question"))
    await asyncio.wait_for(control.started.wait(), timeout=0.1)

    now += DRAFT_TTL * 2

    with pytest.raises(DialogNotFoundError):
        await service.get_dialog(idle_id, OWNER_ID)
    with pytest.raises(DialogNotFoundError):
        await service.subscribe(idle_id, OWNER_ID)
    assert (await service.get_dialog(watched_id, OWNER_ID)).messages == ()
    assert (await service.get_dialog(running_id, OWNER_ID)).messages == ()

    await service.unsubscribe(subscription)
    now += DRAFT_TTL
    with pytest.raises(DialogNotFoundError):
        await service.get_dialog(watched_id, OWNER_ID)
    await service.shutdown()
