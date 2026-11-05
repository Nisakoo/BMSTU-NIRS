import asyncio
import itertools
from abc import ABC, abstractmethod
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from smeshariki_ai.agent import Message, MessageRole
from smeshariki_ai.dialogs.errors import (
    DialogNotFoundError,
    MessageNotFoundError,
    ReportExistsError,
)
from smeshariki_ai.dialogs.models import (
    DialogSummary,
    DialogTranscript,
    ReportNews,
    ReportReason,
    ReportState,
    StoredMessage,
    dialog_title,
)


class HistoryStore(ABC):
    """Dialogs owned by users; a foreign dialog is reported as missing."""

    @abstractmethod
    async def create(self, owner_id: UUID) -> UUID:
        """Create an empty dialog owned by the user and return its identifier."""

    @abstractmethod
    async def get(self, owner_id: UUID, dialog_id: UUID) -> tuple[Message, ...]:
        """Return an immutable snapshot of a dialog history."""

    @abstractmethod
    async def append(
        self,
        dialog_id: UUID,
        messages: Sequence[Message],
    ) -> tuple[int, ...]:
        """Atomically append messages and return their ids in order.

        The first user message names the dialog.
        """

    @abstractmethod
    async def list_dialogs(
        self, owner_id: UUID, *, limit: int
    ) -> tuple[DialogSummary, ...]:
        """Return non-empty dialogs of the user, most recently updated first."""

    @abstractmethod
    async def transcript(self, owner_id: UUID, dialog_id: UUID) -> DialogTranscript:
        """Return the title and the stored messages of a dialog."""

    @abstractmethod
    async def delete(self, owner_id: UUID, dialog_id: UUID) -> None:
        """Delete the user's dialog with its messages and ratings."""

    @abstractmethod
    async def set_feedback(
        self,
        owner_id: UUID,
        dialog_id: UUID,
        message_id: int,
        score: int,
    ) -> None:
        """Rate an assistant answer in the user's own dialog with 1 to 5."""

    @abstractmethod
    async def clear_feedback(
        self, owner_id: UUID, dialog_id: UUID, message_id: int
    ) -> None:
        """Remove the rating of an answer; removing a missing rating is a no-op."""

    @abstractmethod
    async def report(
        self,
        owner_id: UUID,
        dialog_id: UUID,
        message_id: int,
        reason: ReportReason,
        comment: str | None,
    ) -> int:
        """Report an assistant answer in the user's own dialog; return the report id.

        The report keeps copies of the answer and of the user request before
        it, so it outlives the dialog. A second report of the same answer
        raises ``ReportExistsError``.
        """

    @abstractmethod
    async def report_news(
        self, owner_id: UUID, *, limit: int
    ) -> tuple[ReportNews, ...]:
        """Return the user's reviewed reports not yet seen, latest reviewed first."""

    @abstractmethod
    async def mark_report_news_seen(
        self, owner_id: UUID, report_ids: Collection[int]
    ) -> int:
        """Mark the user's reviewed, unseen reports among ``report_ids`` as seen.

        Other ids are skipped; return how many reports were marked.
        """


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class StoredReport:
    """A report kept by ``InMemoryHistoryStore``; ``message_id`` is lost with the dialog."""

    id: int
    message_id: int | None
    user_id: UUID
    reason: ReportReason
    comment: str | None
    request_text: str | None
    answer_text: str
    created_at: datetime
    status: Literal["new", "resolved", "dismissed"] = "new"
    resolved_at: datetime | None = None
    seen_at: datetime | None = None

    @property
    def state(self) -> ReportState:
        return ReportState.SENT if self.status == "new" else ReportState.REVIEWED


@dataclass
class _Dialog:
    owner_id: UUID
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    messages: list[StoredMessage] = field(default_factory=list)


class InMemoryHistoryStore(HistoryStore):
    def __init__(self, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._dialogs: dict[UUID, _Dialog] = {}
        self._feedback: dict[int, int] = {}
        self._reports: dict[int, StoredReport] = {}
        self._message_ids = itertools.count(1)
        self._report_ids = itertools.count(1)
        self._clock = clock
        self._lock = asyncio.Lock()

    async def create(self, owner_id: UUID) -> UUID:
        async with self._lock:
            dialog_id = uuid4()
            while dialog_id in self._dialogs:
                dialog_id = uuid4()
            now = self._clock()
            self._dialogs[dialog_id] = _Dialog(
                owner_id=owner_id, created_at=now, updated_at=now
            )
            return dialog_id

    async def get(self, owner_id: UUID, dialog_id: UUID) -> tuple[Message, ...]:
        async with self._lock:
            dialog = self._owned(owner_id, dialog_id)
            return tuple(
                Message(role=item.role, content=item.content)
                for item in dialog.messages
            )

    async def append(
        self,
        dialog_id: UUID,
        messages: Sequence[Message],
    ) -> tuple[int, ...]:
        async with self._lock:
            try:
                dialog = self._dialogs[dialog_id]
            except KeyError as error:
                raise DialogNotFoundError(dialog_id) from error
            now = self._clock()
            stored = [
                StoredMessage(
                    id=next(self._message_ids),
                    role=item.role,
                    content=item.content,
                    created_at=now,
                )
                for item in messages
            ]
            dialog.messages.extend(stored)
            if dialog.title is None:
                dialog.title = next(
                    (
                        dialog_title(item.content)
                        for item in messages
                        if item.role is MessageRole.USER
                    ),
                    None,
                )
            dialog.updated_at = now
            return tuple(item.id for item in stored)

    async def list_dialogs(
        self, owner_id: UUID, *, limit: int
    ) -> tuple[DialogSummary, ...]:
        async with self._lock:
            summaries = [
                DialogSummary(
                    dialog_id=dialog_id,
                    title=dialog.title,
                    created_at=dialog.created_at,
                    updated_at=dialog.updated_at,
                )
                for dialog_id, dialog in self._dialogs.items()
                if dialog.owner_id == owner_id and dialog.messages
            ]
        summaries.sort(key=lambda summary: summary.updated_at, reverse=True)
        return tuple(summaries[:limit])

    async def transcript(self, owner_id: UUID, dialog_id: UUID) -> DialogTranscript:
        async with self._lock:
            dialog = self._owned(owner_id, dialog_id)
            return DialogTranscript(
                dialog_id=dialog_id,
                title=dialog.title,
                messages=tuple(
                    replace(
                        item,
                        feedback=self._feedback.get(item.id),
                        report=self._report_state(item.id),
                    )
                    for item in dialog.messages
                ),
            )

    async def delete(self, owner_id: UUID, dialog_id: UUID) -> None:
        async with self._lock:
            dialog = self._owned(owner_id, dialog_id)
            for item in dialog.messages:
                self._feedback.pop(item.id, None)
            # Reports stay for the administrator, detached from the dialog.
            ids = {item.id for item in dialog.messages}
            for report in list(self._reports.values()):
                if report.message_id in ids:
                    self._reports[report.id] = replace(report, message_id=None)
            del self._dialogs[dialog_id]

    async def set_feedback(
        self,
        owner_id: UUID,
        dialog_id: UUID,
        message_id: int,
        score: int,
    ) -> None:
        async with self._lock:
            self._answer(owner_id, dialog_id, message_id)
            self._feedback[message_id] = score

    async def clear_feedback(
        self, owner_id: UUID, dialog_id: UUID, message_id: int
    ) -> None:
        async with self._lock:
            self._answer(owner_id, dialog_id, message_id)
            self._feedback.pop(message_id, None)

    async def report(
        self,
        owner_id: UUID,
        dialog_id: UUID,
        message_id: int,
        reason: ReportReason,
        comment: str | None,
    ) -> int:
        async with self._lock:
            self._answer(owner_id, dialog_id, message_id)
            if self._report_state(message_id) is not None:
                raise ReportExistsError(dialog_id, message_id)
            history = self._dialogs[dialog_id].messages
            position = next(
                index for index, item in enumerate(history) if item.id == message_id
            )
            request = next(
                (
                    item.content
                    for item in reversed(history[:position])
                    if item.role is MessageRole.USER
                ),
                None,
            )
            report = StoredReport(
                id=next(self._report_ids),
                message_id=message_id,
                user_id=owner_id,
                reason=reason,
                comment=comment,
                request_text=request,
                answer_text=history[position].content,
                created_at=self._clock(),
            )
            self._reports[report.id] = report
            return report.id

    async def report_news(
        self, owner_id: UUID, *, limit: int
    ) -> tuple[ReportNews, ...]:
        async with self._lock:
            unseen = sorted(
                (
                    report
                    for report in self._reports.values()
                    if report.user_id == owner_id
                    and report.state is ReportState.REVIEWED
                    and report.seen_at is None
                ),
                key=lambda report: (report.resolved_at, report.id),
                reverse=True,
            )
            return tuple(self._news(report) for report in unseen[:limit])

    async def mark_report_news_seen(
        self, owner_id: UUID, report_ids: Collection[int]
    ) -> int:
        async with self._lock:
            now = self._clock()
            marked = 0
            for report_id in set(report_ids):
                report = self._reports.get(report_id)
                if (
                    report is None
                    or report.user_id != owner_id
                    or report.state is not ReportState.REVIEWED
                    or report.seen_at is not None
                ):
                    continue
                self._reports[report_id] = replace(report, seen_at=now)
                marked += 1
            return marked

    def set_report_status(
        self, report_id: int, status: Literal["new", "resolved", "dismissed"]
    ) -> None:
        """Do what the administrator does to a report, for tests."""

        report = self._reports[report_id]
        if status == "new":
            report = replace(report, status=status, resolved_at=None, seen_at=None)
        else:
            report = replace(report, status=status, resolved_at=self._clock())
        self._reports[report_id] = report

    def reports(self) -> tuple[StoredReport, ...]:
        """Reports in the order they were made, for tests."""

        return tuple(self._reports.values())

    def _news(self, report: StoredReport) -> ReportNews:
        for dialog_id, dialog in self._dialogs.items():
            if any(item.id == report.message_id for item in dialog.messages):
                return ReportNews(report.id, dialog_id, dialog.title)
        return ReportNews(report.id, None, None)

    def _report_state(self, message_id: int) -> ReportState | None:
        return next(
            (
                report.state
                for report in self._reports.values()
                if report.message_id == message_id
            ),
            None,
        )

    def _answer(self, owner_id: UUID, dialog_id: UUID, message_id: int) -> None:
        dialog = self._dialogs.get(dialog_id)
        if (
            dialog is None
            or dialog.owner_id != owner_id
            or not any(
                item.id == message_id and item.role is MessageRole.ASSISTANT
                for item in dialog.messages
            )
        ):
            raise MessageNotFoundError(dialog_id, message_id)

    def _owned(self, owner_id: UUID, dialog_id: UUID) -> _Dialog:
        dialog = self._dialogs.get(dialog_id)
        if dialog is None or dialog.owner_id != owner_id:
            raise DialogNotFoundError(dialog_id)
        return dialog
