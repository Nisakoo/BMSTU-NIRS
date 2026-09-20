from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DialogEventType(StrEnum):
    MESSAGE_START = "message_start"
    MESSAGE_DELTA = "message_delta"
    MESSAGE_END = "message_end"
    MESSAGE_ERROR = "message_error"


class DialogEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: DialogEventType
    delta: str | None = None
    code: str | None = None
    message: str | None = None


class DialogSubscription(Protocol):
    @property
    def dialog_id(self) -> UUID: ...

    @property
    def closed(self) -> bool: ...

    async def receive(self) -> DialogEvent | None: ...
