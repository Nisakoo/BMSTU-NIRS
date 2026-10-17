from uuid import UUID


class DialogError(Exception):
    """Base error for dialog operations."""


class DialogNotFoundError(DialogError):
    """The dialog does not exist or belongs to another user."""

    def __init__(self, dialog_id: UUID) -> None:
        self.dialog_id = dialog_id
        super().__init__(f"Dialog not found: {dialog_id}")


class MessageNotFoundError(DialogError):
    """No assistant answer with this id in a dialog the user owns."""

    def __init__(self, dialog_id: UUID, message_id: int) -> None:
        self.dialog_id = dialog_id
        self.message_id = message_id
        super().__init__(f"Message not found: {dialog_id}/{message_id}")


class DialogStoreUnavailableError(DialogError):
    """The history storage failed; the caller must not assume any change."""
