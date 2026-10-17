TITLE_MAX_LENGTH = 60
_ELLIPSIS = "…"


def make_title(text: str) -> str:
    """Build a dialog title from the first user request."""

    normalized = " ".join(text.split())
    if len(normalized) <= TITLE_MAX_LENGTH:
        return normalized
    return normalized[:TITLE_MAX_LENGTH] + _ELLIPSIS
