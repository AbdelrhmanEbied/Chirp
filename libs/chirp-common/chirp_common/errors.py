from __future__ import annotations

from typing import Any

class AppError(Exception):

    status_code: int = 500
    code: str = "internal_error"
    message: str = "Internal server error."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or type(self).message
        self.code = code or type(self).code
        self.details = details or {}
        self.status_code = status_code or type(self).status_code
        super().__init__(self.message)

    def to_payload(self, request_id: str | None = None) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        if request_id:
            error["request_id"] = request_id
        return {"error": error}

class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"
    message = "The request was malformed."

class ValidationError(AppError):
    status_code = 422
    code = "validation_error"
    message = "The request failed validation."

class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Authentication is required."

class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message = "You do not have access to this resource."

class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "The requested resource does not exist."

class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "The request conflicts with the current state."

class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests."

    def __init__(self, retry_after_seconds: int = 60, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.retry_after_seconds = retry_after_seconds

class DependencyError(AppError):

    status_code = 502
    code = "dependency_unavailable"
    message = "A downstream dependency is unavailable."

class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "The service is temporarily unavailable."
