"""Application-specific exceptions and HTTP error payloads."""

from typing import Any


class AppException(Exception):
    """Base application error."""

    def __init__(self, message: str, code: str = "app_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ConfigurationError(AppException):
    """Invalid or incomplete configuration."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="configuration_error")


class SecretNotFoundError(AppException):
    """Required secret missing from provider."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="secret_not_found")


class AgentInvocationError(AppException):
    """Agent graph or tool execution failed."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="agent_error")


def error_payload(
    *,
    message: str,
    code: str,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable error body."""
    body: dict[str, Any] = {"error": message, "code": code}
    if request_id:
        body["request_id"] = request_id
    if details:
        body["details"] = details
    return body
