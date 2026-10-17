from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from smeshariki_ai.agent import MessageRole


class DialogModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DialogSummary(DialogModel):
    dialog_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class DialogCursor(DialogModel):
    updated_at: datetime
    dialog_id: UUID


class StoredMessage(DialogModel):
    role: MessageRole
    content: str
    created_at: datetime


class DialogTranscript(DialogModel):
    title: str | None
    messages: tuple[StoredMessage, ...]
