class ApplicationServiceError(Exception):
    """Base error for application service operations."""


class AgentServiceUnavailableError(ApplicationServiceError):
    """Raised when the service can no longer accept background work."""
