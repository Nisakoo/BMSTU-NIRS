import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from smeshariki_ai.agent import (
    AgentResponse,
    AgentStreamEvent,
    AgentTextDelta,
    Message,
    MessageRole,
    UserRequest,
)
from smeshariki_ai.application.errors import AgentServiceUnavailableError
from smeshariki_ai.application.event_broker import DialogEventBroker
from smeshariki_ai.application.events import (
    DialogEvent,
    DialogEventType,
    DialogSubscription,
)
from smeshariki_ai.dialogs import (
    DialogCursor,
    DialogDrafts,
    DialogNotFoundError,
    DialogSummary,
    DialogTranscript,
    HistoryStore,
    make_title,
)
from smeshariki_ai.observability import bind_context, log_event, utc_now

logger = logging.getLogger(__name__)


class AgentRunner(Protocol):
    def run(
        self,
        history: Sequence[Message],
        request: UserRequest,
    ) -> AsyncIterator[AgentStreamEvent]: ...


@dataclass(frozen=True)
class DialogPage:
    items: tuple[DialogSummary, ...]
    next_cursor: DialogCursor | None


def _utc_clock() -> datetime:
    return datetime.now(UTC)


class AgentService:
    def __init__(
        self,
        agent: AgentRunner,
        history_store: HistoryStore,
        event_broker: DialogEventBroker,
        *,
        drafts: DialogDrafts | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._agent = agent
        self._history_store = history_store
        self._event_broker = event_broker
        self._clock = clock or _utc_clock
        self._drafts = drafts or DialogDrafts(clock=self._clock)
        self._state_lock = asyncio.Lock()
        self._accepting = True
        self._dialog_tails: dict[UUID, asyncio.Task[None]] = {}
        self._dialog_tasks: dict[UUID, set[asyncio.Task[None]]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._started_tasks: set[asyncio.Task[None]] = set()
        self._deleting: set[UUID] = set()
        self._draft_subscriptions: set[DialogSubscription] = set()

    async def start_dialog(self, user_id: UUID) -> UUID:
        async with self._state_lock:
            self._ensure_accepting()
            dialog_id = self._drafts.create(user_id)

        log_event(logger, logging.INFO, "dialog.created", dialog_id=str(dialog_id))
        return dialog_id

    async def submit(
        self, dialog_id: UUID, user_id: UUID, request: UserRequest
    ) -> None:
        await self._ensure_owner(dialog_id, user_id)

        async with self._state_lock:
            self._ensure_accepting()
            self._ensure_not_deleting(dialog_id)
            previous_task = self._dialog_tails.get(dialog_id)
            with bind_context(dialog_id=str(dialog_id)):
                task = asyncio.create_task(
                    self._run_after(previous_task, dialog_id, request),
                    name=f"agent-dialog-{dialog_id}",
                )
            self._dialog_tails[dialog_id] = task
            self._dialog_tasks.setdefault(dialog_id, set()).add(task)
            self._tasks.add(task)
            self._drafts.run_started(dialog_id)
            task.add_done_callback(
                lambda completed, current_dialog_id=dialog_id: self._task_done(
                    current_dialog_id,
                    completed,
                )
            )

        log_event(
            logger, logging.INFO, "dialog.request.accepted", dialog_id=str(dialog_id)
        )

    async def subscribe(self, dialog_id: UUID, user_id: UUID) -> DialogSubscription:
        await self._ensure_owner(dialog_id, user_id)
        async with self._state_lock:
            self._ensure_accepting()
            self._ensure_not_deleting(dialog_id)
            subscription = await self._event_broker.subscribe(dialog_id)
            if self._drafts.owner(dialog_id) is not None:
                self._drafts.attach(dialog_id)
                self._draft_subscriptions.add(subscription)
        log_event(
            logger, logging.INFO, "dialog.subscription.opened", dialog_id=str(dialog_id)
        )
        return subscription

    async def unsubscribe(self, subscription: DialogSubscription) -> None:
        await self._event_broker.unsubscribe(subscription)
        if subscription in self._draft_subscriptions:
            self._draft_subscriptions.discard(subscription)
            self._drafts.detach(subscription.dialog_id)
        log_event(
            logger,
            logging.INFO,
            "dialog.subscription.closed",
            dialog_id=str(subscription.dialog_id),
        )

    async def list_dialogs(
        self,
        user_id: UUID,
        limit: int,
        after: DialogCursor | None = None,
    ) -> DialogPage:
        # One extra item tells whether another page exists.
        items = await self._history_store.list(user_id, limit + 1, after)
        page = items[:limit]
        next_cursor = None
        if len(items) > limit:
            last = page[-1]
            next_cursor = DialogCursor(
                updated_at=last.updated_at, dialog_id=last.dialog_id
            )
        return DialogPage(items=page, next_cursor=next_cursor)

    async def get_dialog(self, dialog_id: UUID, user_id: UUID) -> DialogTranscript:
        await self._ensure_owner(dialog_id, user_id)
        if self._drafts.owner(dialog_id) is not None:
            return DialogTranscript(title=None, messages=())
        return await self._history_store.read(dialog_id)

    async def delete_dialog(self, dialog_id: UUID, user_id: UUID) -> None:
        await self._ensure_owner(dialog_id, user_id)
        async with self._state_lock:
            self._ensure_accepting()
            self._ensure_not_deleting(dialog_id)
            self._deleting.add(dialog_id)
            tasks = tuple(self._dialog_tasks.get(dialog_id, ()))
            # A task cancelled before its first step never reports the error.
            unstarted = any(task not in self._started_tasks for task in tasks)
            for task in tasks:
                task.cancel()

        try:
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if unstarted:
                await self._publish_error(dialog_id)
            # Checked after the runs ended: a run may have saved the draft first.
            is_draft = self._drafts.owner(dialog_id) is not None
            if is_draft and tasks:
                # The first save may have committed just before the cancellation.
                with suppress(DialogNotFoundError):
                    await self._history_store.delete(dialog_id)
            if is_draft:
                self._drafts.discard(dialog_id)
            else:
                await self._history_store.delete(dialog_id)
            await self._event_broker.close_dialog(dialog_id)
        finally:
            self._deleting.discard(dialog_id)

        log_event(
            logger,
            logging.INFO,
            "dialog.deleted",
            dialog_id=str(dialog_id),
            user_id=str(user_id),
            draft=is_draft,
        )

    async def shutdown(self) -> None:
        async with self._state_lock:
            self._accepting = False
            tasks = tuple(self._tasks)
            for task in tasks:
                task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._tasks.clear()
        self._dialog_tails.clear()
        self._dialog_tasks.clear()
        await self._event_broker.shutdown()

    async def _run_after(
        self,
        previous_task: asyncio.Task[None] | None,
        dialog_id: UUID,
        request: UserRequest,
    ) -> None:
        current_task = asyncio.current_task()
        assert current_task is not None
        self._started_tasks.add(current_task)
        started_at = utc_now()
        started = time.monotonic()
        try:
            if previous_task is not None:
                await previous_task

            log_event(
                logger, logging.INFO, "dialog.run.started", dialog_id=str(dialog_id)
            )
            await self._event_broker.publish(
                dialog_id,
                DialogEvent(type=DialogEventType.MESSAGE_START),
            )
            draft_owner = self._drafts.owner(dialog_id)
            history = () if draft_owner else await self._history_store.get(dialog_id)
            response: AgentResponse | None = None
            async for event in self._agent.run(history, request):
                if isinstance(event, AgentTextDelta):
                    await self._event_broker.publish(
                        dialog_id,
                        DialogEvent(
                            type=DialogEventType.MESSAGE_DELTA,
                            delta=event.content,
                        ),
                    )
                elif isinstance(event, AgentResponse):
                    response = event

            if response is None:
                raise RuntimeError("Agent stream ended without a response.")
            messages = (
                Message(role=MessageRole.USER, content=request.content),
                Message(role=MessageRole.ASSISTANT, content=response.content),
            )
            now = self._clock()
            if draft_owner is None:
                await self._history_store.append(dialog_id, messages, now)
            else:
                await self._history_store.create(
                    dialog_id,
                    draft_owner,
                    make_title(request.content),
                    messages,
                    now,
                )
                self._drafts.discard(dialog_id)
                log_event(
                    logger,
                    logging.INFO,
                    "dialog.persisted",
                    dialog_id=str(dialog_id),
                )
            log_event(
                logger,
                logging.INFO,
                "dialog.history.persisted",
                dialog_id=str(dialog_id),
            )
            await self._event_broker.publish(
                dialog_id,
                DialogEvent(type=DialogEventType.MESSAGE_END),
            )
            log_event(
                logger,
                logging.INFO,
                "dialog.run.completed",
                dialog_id=str(dialog_id),
                started_at=started_at,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                outcome="completed",
            )
        except asyncio.CancelledError:
            await self._publish_error(dialog_id)
            log_event(
                logger,
                logging.INFO,
                "dialog.run.cancelled",
                dialog_id=str(dialog_id),
                started_at=started_at,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                outcome="cancelled",
            )
            raise
        except Exception as error:
            await self._publish_error(dialog_id)
            log_event(
                logger,
                logging.ERROR,
                "dialog.run.failed",
                dialog_id=str(dialog_id),
                error_type=type(error).__name__,
                started_at=started_at,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                outcome="failed",
            )

    async def _publish_error(self, dialog_id: UUID) -> None:
        await self._event_broker.publish(
            dialog_id,
            DialogEvent(
                type=DialogEventType.MESSAGE_ERROR,
                code="agent_error",
                message="Agent request failed.",
            ),
        )

    def _task_done(self, dialog_id: UUID, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        self._started_tasks.discard(task)
        if self._dialog_tails.get(dialog_id) is task:
            self._dialog_tails.pop(dialog_id, None)
        dialog_tasks = self._dialog_tasks.get(dialog_id)
        if dialog_tasks is not None:
            dialog_tasks.discard(task)
            if not dialog_tasks:
                del self._dialog_tasks[dialog_id]
        self._drafts.run_finished(dialog_id)

        try:
            task.exception()
        except asyncio.CancelledError:
            pass

    async def _ensure_owner(self, dialog_id: UUID, user_id: UUID) -> None:
        # A foreign dialog is reported as missing; only the log tells them apart.
        if dialog_id in self._deleting:
            raise DialogNotFoundError(dialog_id)
        owner_id = self._drafts.owner(dialog_id)
        if owner_id is None:
            owner_id = await self._history_store.owner(dialog_id)
        if owner_id != user_id:
            log_event(
                logger,
                logging.INFO,
                "dialog.access.denied",
                dialog_id=str(dialog_id),
                user_id=str(user_id),
                outcome="foreign",
            )
            raise DialogNotFoundError(dialog_id)

    def _ensure_not_deleting(self, dialog_id: UUID) -> None:
        if dialog_id in self._deleting:
            raise DialogNotFoundError(dialog_id)

    def _ensure_accepting(self) -> None:
        if not self._accepting:
            raise AgentServiceUnavailableError(
                "The agent service is not accepting new requests."
            )
