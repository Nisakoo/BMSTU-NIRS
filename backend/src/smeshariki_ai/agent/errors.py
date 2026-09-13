class AgentError(Exception):
    """Base error raised by the agent runtime."""


class InvalidLLMResponseError(AgentError):
    """Raised when an LLM provider returns an unsupported response shape."""


class AgentIterationLimitError(AgentError):
    """Raised when the agent cannot finish within its configured iteration limit."""


class DuplicateToolError(ValueError):
    """Raised when a registry receives more than one tool with the same name."""
