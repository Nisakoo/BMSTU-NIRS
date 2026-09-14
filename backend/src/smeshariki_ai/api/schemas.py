from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

RequestText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartDialogResponse(ApiModel):
    dialog_id: UUID


class SubmitMessageRequest(ApiModel):
    request: RequestText
