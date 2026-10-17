from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

RequestText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartDialogResponse(ApiModel):
    dialog_id: UUID


class SubmitMessageRequest(ApiModel):
    request: RequestText


class DialogSummaryResponse(ApiModel):
    dialog_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class DialogListResponse(ApiModel):
    items: list[DialogSummaryResponse]
    next_cursor: str | None


class StoredMessageResponse(ApiModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class DialogMessagesResponse(ApiModel):
    dialog_id: UUID
    title: str | None
    messages: list[StoredMessageResponse]
