"""Controlled and sanitized service errors from spec.md section 14."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError as FastAPIRequestValidationError
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)


class ControlledServiceError(Exception):
    """Base exception containing only a client-safe message and status."""

    status_code = 500
    error_code = "internal_error"
    default_message = "Internal processing failed."

    def __init__(self, safe_message: str | None = None) -> None:
        self.safe_message = safe_message or self.default_message
        super().__init__(self.safe_message)


class RequestValidationError(ControlledServiceError):
    """Controlled error for malformed or structurally invalid client input."""

    status_code = 400
    error_code = "invalid_request"
    default_message = "Request validation failed."


class InternalProcessingError(ControlledServiceError):
    """Controlled error for failures that cannot safely expose internals."""


def _validation_details(exc: FastAPIRequestValidationError) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", ()) if part != "body"]
        message = str(error.get("msg", "Invalid value."))
        if message.startswith("Value error, "):
            message = message.removeprefix("Value error, ")
        details.append(
            {
                "field": ".".join(location) or "request_body",
                "message": message,
            }
        )
    return details


async def request_validation_exception_handler(
    request: Request, exc: FastAPIRequestValidationError
) -> JSONResponse:
    """Convert FastAPI/Pydantic request failures to a controlled HTTP 400."""

    del request
    return JSONResponse(
        status_code=400,
        content={
            "error": "invalid_request",
            "message": "Request validation failed.",
            "details": _validation_details(exc),
        },
    )


async def controlled_exception_handler(
    request: Request, exc: ControlledServiceError
) -> JSONResponse:
    """Serialize an explicitly controlled service error."""

    del request
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error_code, "message": exc.safe_message},
    )


async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected failures and return a secret-free HTTP 500."""

    logger.exception(
        "Unhandled exception while processing %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "Internal processing failed.",
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the controlled error policy to a FastAPI application."""

    app.add_exception_handler(
        FastAPIRequestValidationError, request_validation_exception_handler
    )
    app.add_exception_handler(ControlledServiceError, controlled_exception_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)
