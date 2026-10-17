from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from smeshariki_ai.agent import MessageRole

TITLE_MAX_LENGTH = 60


@dataclass(frozen=True, slots=True)
class DialogSummary:
    dialog_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


MIN_SCORE = 1
MAX_SCORE = 5


@dataclass(frozen=True, slots=True)
class StoredMessage:
    id: int
    role: MessageRole
    content: str
    created_at: datetime
    feedback: int | None = None


@dataclass(frozen=True, slots=True)
class DialogTranscript:
    dialog_id: UUID
    title: str | None
    messages: tuple[StoredMessage, ...]


def dialog_title(text: str) -> str:
    """Title of a dialog: its first request on one line, cut to 60 characters."""

    title = " ".join(text.split())
    if len(title) <= TITLE_MAX_LENGTH:
        return title
    return title[:TITLE_MAX_LENGTH].rstrip() + "…"
