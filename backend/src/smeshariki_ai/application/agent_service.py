import asyncio
import logging
import time
from collections.abc import AsyncIterator, Sequence
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
from smeshariki_ai.dialogs import HistoryStore
from smeshariki_ai.observability import bind_context, log_event, utc_now

logger = logging.getLogger(__name__)


class AgentRunner(Protocol):
    def run(
        self,
        history: Sequence[Message],
        request: UserRequest,
    ) -> AsyncIterator[AgentStreamEvent]: ...


class AgentService:
    def __init__(
        self,
        agent: AgentRunner,
        history_store: HistoryStore,
        event_broker: DialogEventBroker,
    ) -> None:
        self._agent = agent
        self._history_store = history_store
        self._event_broker = event_broker
        self._state_lock = asyncio.Lock()
        self._accepting = True
        self._dialog_tails: dict[UUID, asyncio.Task[None]] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    async def start_dialog(self) -> UUID:
        async with self._state_lock:
            self._ensure_accepting()
            dialog_id = await self._history_store.create()

        log_event(logger, logging.INFO, "dialog.created", dialog_id=str(dialog_id))
        return dialog_id

    async def submit(self, dialog_id: UUID, request: UserRequest) -> None:
        await self._history_store.get(dialog_id)

        async with self._state_lock:
            self._ensure_accepting()
            previous_task = self._dialog_tails.get(dialog_id)
            with bind_context(dialog_id=str(dialog_id)):
                task = asyncio.create_task(
                    self._run_after(previous_task, dialog_id, request),
                    name=f"agent-dialog-{dialog_id}",
                )
            self._dialog_tails[dialog_id] = task
            self._tasks.add(task)
            task.add_done_callback(
                lambda completed, current_dialog_id=dialog_id: self._task_done(
                    current_dialog_id,
                    completed,
                )
            )

        log_event(
            logger, logging.INFO, "dialog.request.accepted", dialog_id=str(dialog_id)
        )

    async def subscribe(self, dialog_id: UUID) -> DialogSubscription:
        await self._history_store.get(dialog_id)
        async with self._state_lock:
            self._ensure_accepting()
            subscription = await self._event_broker.subscribe(dialog_id)
        log_event(
            logger, logging.INFO, "dialog.subscription.opened", dialog_id=str(dialog_id)
        )
        return subscription

    async def unsubscribe(self, subscription: DialogSubscription) -> None:
        await self._event_broker.unsubscribe(subscription)
        log_event(
            logger,
            logging.INFO,
            "dialog.subscription.closed",
            dialog_id=str(subscription.dialog_id),
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
        await self._event_broker.shutdown()

    async def _run_after(
        self,
        previous_task: asyncio.Task[None] | None,
        dialog_id: UUID,
        request: UserRequest,
    ) -> None:
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
            history = await self._history_store.get(dialog_id)
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
            await self._history_store.append(
                dialog_id,
                (
                    Message(role=MessageRole.USER, content=request.content),
                    Message(role=MessageRole.ASSISTANT, content=response.content),
                ),
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
        if self._dialog_tails.get(dialog_id) is task:
            self._dialog_tails.pop(dialog_id, None)

        try:
            task.exception()
        except asyncio.CancelledError:
            pass

    def _ensure_accepting(self) -> None:
        if not self._accepting:
            raise AgentServiceUnavailableError(
                "The agent service is not accepting new requests."
            )
