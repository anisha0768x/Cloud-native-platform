"""
Standard exception hierarchy + FastAPI exception handlers.

WHY: the frontend (one React codebase talking to 12 services through one
gateway) needs ONE predictable error JSON shape, regardless of which
service produced it:

    {
      "error": {
        "code": "RESOURCE_NOT_FOUND",
        "message": "Service 'checkout-api' not found",
        "details": {...}          # optional, machine-readable extra context
      }
    }

If every service invented its own error format, the frontend would need
per-service error-handling branches — brittle and exactly the kind of
inconsistency this shared library exists to prevent.
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class PlatformError(Exception):
    """Base class for all deliberate, expected application errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(PlatformError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "RESOURCE_NOT_FOUND"


class ValidationError(PlatformError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "VALIDATION_ERROR"


class UnauthorizedError(PlatformError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"


class ForbiddenError(PlatformError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"


class ConflictError(PlatformError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class DependencyUnavailableError(PlatformError):
    """Raised when a downstream dependency (DB, Kafka, another service) is down."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "DEPENDENCY_UNAVAILABLE"


def _error_response(exc: PlatformError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """
    Call once per service: `register_exception_handlers(app)` in main.py.
    Ensures unhandled PlatformError subclasses AND unexpected exceptions
    both still return the standard error shape instead of a raw traceback.
    """

    @app.exception_handler(PlatformError)
    async def _platform_error_handler(request: Request, exc: PlatformError) -> JSONResponse:
        return _error_response(exc)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Never leak internal exception details to the client; log instead.
        import logging

        logging.getLogger("platform_common.exceptions").exception(
            "Unhandled exception", extra={"path": str(request.url)}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                    "details": {},
                }
            },
        )
