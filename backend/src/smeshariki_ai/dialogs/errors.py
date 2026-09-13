from uuid import UUID


class DialogError(Exception):
    """Base error for dialog operations."""


class DialogNotFoundError(DialogError):
    def __init__(self, dialog_id: UUID) -> None:
        self.dialog_id = dialog_id
        super().__init__(f"Dialog not found: {dialog_id}")
