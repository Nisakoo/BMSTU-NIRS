from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints

from smeshariki_ai.agent.models import ReadingMinutes
from smeshariki_ai.dialogs import MAX_SCORE, MIN_SCORE

RequestText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartDialogResponse(ApiModel):
    dialog_id: UUID


class SubmitMessageRequest(ApiModel):
    request: RequestText
    # Optional, but an explicit null is rejected like any unsupported value.
    reading_minutes: ReadingMinutes = None  # type: ignore[assignment]


class DialogSummaryResponse(ApiModel):
    dialog_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class DialogListResponse(ApiModel):
    dialogs: list[DialogSummaryResponse]


Score = Annotated[StrictInt, Field(ge=MIN_SCORE, le=MAX_SCORE)]


class DialogMessageResponse(ApiModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    feedback: Score | None


class DialogMessagesResponse(ApiModel):
    dialog_id: UUID
    title: str | None
    messages: list[DialogMessageResponse]


class FeedbackRequest(ApiModel):
    score: Score
