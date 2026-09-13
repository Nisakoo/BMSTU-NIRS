import asyncio
import logging
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from smeshariki_ai.agent import AgentResponse, Message, MessageRole, UserRequest
from smeshariki_ai.application.errors import AgentServiceUnavailableError
from smeshariki_ai.dialogs import HistoryStore

logger = logging.getLogger(__name__)


class AgentRunner(Protocol):
    async def run(
        self,
        history: Sequence[Message],
        request: UserRequest,
    ) -> AgentResponse: ...


class AgentService:
    def __init__(self, agent: AgentRunner, history_store: HistoryStore) -> None:
        self._agent = agent
        self._history_store = history_store
        self._state_lock = asyncio.Lock()
        self._accepting = True
        self._dialog_tails: dict[UUID, asyncio.Task[None]] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    async def start_dialog(self) -> UUID:
        async with self._state_lock:
            self._ensure_accepting()
            dialog_id = await self._history_store.create()

        logger.info(
            "dialog.created dialog_id=%s",
            dialog_id,
            extra={"dialog_id": str(dialog_id)},
        )
        return dialog_id

    async def submit(self, dialog_id: UUID, request: UserRequest) -> None:
        await self._history_store.get(dialog_id)

        async with self._state_lock:
            self._ensure_accepting()
            previous_task = self._dialog_tails.get(dialog_id)
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

        logger.info(
            "dialog.request.accepted dialog_id=%s",
            dialog_id,
            extra={"dialog_id": str(dialog_id)},
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

    async def _run_after(
        self,
        previous_task: asyncio.Task[None] | None,
        dialog_id: UUID,
        request: UserRequest,
    ) -> None:
        try:
            if previous_task is not None:
                await previous_task

            logger.info(
                "dialog.run.started dialog_id=%s",
                dialog_id,
                extra={"dialog_id": str(dialog_id)},
            )
            history = await self._history_store.get(dialog_id)
            response = await self._agent.run(history, request)
            logger.info(
                "dialog.run.completed dialog_id=%s",
                dialog_id,
                extra={"dialog_id": str(dialog_id)},
            )

            await self._history_store.append(
                dialog_id,
                (
                    Message(role=MessageRole.USER, content=request.content),
                    Message(role=MessageRole.ASSISTANT, content=response.content),
                ),
            )
            logger.info(
                "dialog.history.persisted dialog_id=%s",
                dialog_id,
                extra={"dialog_id": str(dialog_id)},
            )
        except asyncio.CancelledError:
            logger.info(
                "dialog.run.cancelled dialog_id=%s",
                dialog_id,
                extra={"dialog_id": str(dialog_id)},
            )
            raise
        except Exception as error:
            logger.error(
                "dialog.run.failed dialog_id=%s error_type=%s",
                dialog_id,
                type(error).__name__,
                extra={
                    "dialog_id": str(dialog_id),
                    "error_type": type(error).__name__,
                },
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
