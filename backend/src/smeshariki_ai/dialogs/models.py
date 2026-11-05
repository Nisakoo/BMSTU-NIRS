from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from smeshariki_ai.agent import MessageRole

# Long enough for a whole request; the page cuts it to the available width.
TITLE_MAX_LENGTH = 200


@dataclass(frozen=True, slots=True)
class DialogSummary:
    dialog_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


MIN_SCORE = 1
MAX_SCORE = 5

REPORT_COMMENT_MAX_LENGTH = 500
REPORT_NEWS_LIMIT = 20


class ReportReason(StrEnum):
    """Why a user reports an answer as unfit for children."""

    SCARY = "scary"
    RUDE = "rude"
    WRONG = "wrong"
    OTHER = "other"


class ReportState(StrEnum):
    """What the user may know about a report: not whether it was dismissed."""

    SENT = "sent"
    REVIEWED = "reviewed"


@dataclass(frozen=True, slots=True)
class StoredMessage:
    id: int
    role: MessageRole
    content: str
    created_at: datetime
    feedback: int | None = None
    report: ReportState | None = None

    @property
    def reported(self) -> bool:
        return self.report is not None


@dataclass(frozen=True, slots=True)
class ReportNews:
    """A reviewed report the user has not dismissed yet; no dialog once deleted."""

    report_id: int
    dialog_id: UUID | None
    dialog_title: str | None


@dataclass(frozen=True, slots=True)
class DialogTranscript:
    dialog_id: UUID
    title: str | None
    messages: tuple[StoredMessage, ...]


def dialog_title(text: str) -> str:
    """Title of a dialog: its first request on one line, cut to 200 characters."""

    title = " ".join(text.split())
    if len(title) <= TITLE_MAX_LENGTH:
        return title
    return title[:TITLE_MAX_LENGTH].rstrip() + "…"
