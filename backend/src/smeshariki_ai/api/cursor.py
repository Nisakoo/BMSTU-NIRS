"""Opaque pagination cursor of the dialog list (see docs/dialogs.md)."""

import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from smeshariki_ai.dialogs import DialogCursor


class InvalidCursorError(ValueError):
    """Raised when a cursor cannot be decoded."""


def encode_cursor(cursor: DialogCursor) -> str:
    payload = json.dumps(
        {"u": cursor.updated_at.isoformat(), "d": str(cursor.dialog_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()


def decode_cursor(value: str) -> DialogCursor:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        updated_at = datetime.fromisoformat(payload["u"])
        if updated_at.tzinfo is None:
            raise InvalidCursorError
        return DialogCursor(updated_at=updated_at, dialog_id=UUID(payload["d"]))
    except InvalidCursorError:
        raise
    except (
        binascii.Error,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
    ) as error:
        raise InvalidCursorError from error
