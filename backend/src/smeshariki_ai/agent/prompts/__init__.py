from importlib import resources

_SYSTEM_PROMPT_RESOURCE = "system.md"


class SystemPromptResourceError(RuntimeError):
    """Raised when the production system prompt cannot be loaded safely."""


def load_system_prompt() -> str:
    try:
        prompt = (
            resources.files(__package__)
            .joinpath(_SYSTEM_PROMPT_RESOURCE)
            .read_text(encoding="utf-8")
            .strip()
        )
    except (OSError, UnicodeError):
        raise SystemPromptResourceError(
            "System prompt resource could not be read."
        ) from None

    if not prompt:
        raise SystemPromptResourceError("System prompt resource is empty.")

    return prompt


__all__ = ["SystemPromptResourceError", "load_system_prompt"]
