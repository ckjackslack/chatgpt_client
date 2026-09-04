from __future__ import annotations


class ChatGPTClientError(Exception):
    """Base class for expected, user-facing application failures."""


class ConfigurationError(ChatGPTClientError, ValueError):
    """Raised when application configuration is missing or malformed."""


class RepositoryError(ChatGPTClientError):
    """Raised when local history cannot be initialized or accessed."""


class DatabaseError(RepositoryError):
    """Raised when the SQLite infrastructure cannot complete an operation."""


class UsageError(ChatGPTClientError, ValueError):
    """Raised when a valid CLI command would perform an unsafe operation."""


class ResponseGenerationError(ChatGPTClientError):
    """Raised when OpenAI cannot generate a usable text response."""

    def __init__(
        self,
        message: str,
        *,
        request_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.request_id = request_id
        self.status_code = status_code

    def __str__(self) -> str:
        details: list[str] = []
        if self.status_code is not None:
            details.append(f"status={self.status_code}")
        if self.request_id:
            details.append(f"request_id={self.request_id}")
        suffix = f" ({', '.join(details)})" if details else ""
        return f"{super().__str__()}{suffix}"
