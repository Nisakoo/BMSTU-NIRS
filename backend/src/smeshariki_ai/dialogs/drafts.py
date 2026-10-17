import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from smeshariki_ai.observability import log_event

DRAFT_TTL = timedelta(minutes=30)
logger = logging.getLogger(__name__)


def _utc_clock() -> datetime:
    return datetime.now(UTC)


@dataclass
class _Draft:
    owner_id: UUID
    subscriptions: int
    runs: int
    last_activity: datetime


class DialogDrafts:
    """Process-local dialogs that are not stored until the first agent answer.

    A draft expires lazily, on the next access, once it has had no
    subscriptions and no runs for ``ttl``.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = _utc_clock,
        ttl: timedelta = DRAFT_TTL,
    ) -> None:
        self._clock = clock
        self._ttl = ttl
        self._drafts: dict[UUID, _Draft] = {}

    def create(self, owner_id: UUID) -> UUID:
        self._expire_all()
        dialog_id = uuid4()
        while dialog_id in self._drafts:
            dialog_id = uuid4()
        self._drafts[dialog_id] = _Draft(owner_id, 0, 0, self._clock())
        return dialog_id

    def owner(self, dialog_id: UUID) -> UUID | None:
        draft = self._find(dialog_id)
        return None if draft is None else draft.owner_id

    def attach(self, dialog_id: UUID) -> None:
        draft = self._find(dialog_id)
        if draft is not None:
            draft.subscriptions += 1
            draft.last_activity = self._clock()

    def detach(self, dialog_id: UUID) -> None:
        draft = self._find(dialog_id)
        if draft is not None:
            draft.subscriptions = max(0, draft.subscriptions - 1)
            draft.last_activity = self._clock()

    def run_started(self, dialog_id: UUID) -> None:
        draft = self._find(dialog_id)
        if draft is not None:
            draft.runs += 1
            draft.last_activity = self._clock()

    def run_finished(self, dialog_id: UUID) -> None:
        draft = self._find(dialog_id)
        if draft is not None:
            draft.runs = max(0, draft.runs - 1)
            draft.last_activity = self._clock()

    def discard(self, dialog_id: UUID) -> None:
        self._drafts.pop(dialog_id, None)

    def _find(self, dialog_id: UUID) -> _Draft | None:
        draft = self._drafts.get(dialog_id)
        if draft is not None and self._is_expired(draft):
            self._expire(dialog_id)
            return None
        return draft

    def _is_expired(self, draft: _Draft) -> bool:
        return (
            draft.subscriptions == 0
            and draft.runs == 0
            and self._clock() - draft.last_activity >= self._ttl
        )

    def _expire_all(self) -> None:
        for dialog_id, draft in tuple(self._drafts.items()):
            if self._is_expired(draft):
                self._expire(dialog_id)

    def _expire(self, dialog_id: UUID) -> None:
        del self._drafts[dialog_id]
        log_event(
            logger, logging.INFO, "dialog.draft.expired", dialog_id=str(dialog_id)
        )
