from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Path
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from smeshariki_ai.agent.models import ReadingMinutes
from smeshariki_ai.dialogs import (
    MAX_SCORE,
    MIN_SCORE,
    REPORT_COMMENT_MAX_LENGTH,
    REPORT_NEWS_LIMIT,
    ReportReason,
    ReportState,
)

RequestText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

# Message and report ids are PostgreSQL BIGINT identities.
MAX_DB_ID = 2**63 - 1
DbId = Annotated[StrictInt, Field(ge=1, le=MAX_DB_ID)]
DbIdPath = Annotated[int, Path(ge=1, le=MAX_DB_ID)]


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
    reported: bool
    report: ReportState | None


class DialogMessagesResponse(ApiModel):
    dialog_id: UUID
    title: str | None
    messages: list[DialogMessageResponse]


class FeedbackRequest(ApiModel):
    score: Score


class ReportRequest(ApiModel):
    reason: ReportReason
    comment: (
        Annotated[
            StrictStr,
            StringConstraints(
                strip_whitespace=True, max_length=REPORT_COMMENT_MAX_LENGTH
            ),
        ]
        | None
    ) = None

    @field_validator("comment")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def other_needs_a_comment(self) -> "ReportRequest":
        # Only "other" does not say by itself what is wrong with the answer.
        if self.reason is ReportReason.OTHER and self.comment is None:
            raise ValueError("A comment is required for the reason 'other'.")
        return self


class ReportResponse(ApiModel):
    report_id: int


class ReportNewsItem(ApiModel):
    report_id: int
    dialog_id: UUID | None
    dialog_title: str | None


class ReportNewsResponse(ApiModel):
    news: list[ReportNewsItem]


class ReportNewsSeenRequest(ApiModel):
    report_ids: Annotated[list[DbId], Field(min_length=1, max_length=REPORT_NEWS_LIMIT)]
