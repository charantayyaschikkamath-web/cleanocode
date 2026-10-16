from __future__ import annotations

from typing import Any


class DomainError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(DomainError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            "RESOURCE_NOT_FOUND",
            f"{resource} '{resource_id}' was not found.",
            status_code=404,
            details={"resource": resource, "id": resource_id},
        )


class ConflictError(DomainError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(code, message, status_code=409, details=details)
