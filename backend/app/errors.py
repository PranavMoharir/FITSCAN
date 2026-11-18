"""The standard error envelope (HLD §12.1, LLD §4.4).

Every error response has the same shape:

    {"error": {"code": "...", "message": "...", "details": {...}}}

`AppError` is raised for known errors (unknown ID, invalid state, unavailable service).
The handlers below also convert FastAPI's own errors (unknown route, validation failure)
and unexpected exceptions into this shape, so the frontend handles every error the same way.
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """A known error with an HTTP status, a stable code and a readable message."""

    def __init__(self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_response(status_code: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content={"error": body})


async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def _handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    # FastAPI raises these itself, e.g. 404 for an unknown path or 405 for a wrong method.
    # The code is the standard HTTP status name, e.g. NOT_FOUND or METHOD_NOT_ALLOWED.
    status = HTTPStatus(exc.status_code)
    message = exc.detail if isinstance(exc.detail, str) else status.phrase
    return error_response(exc.status_code, status.name, message)


async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Only the field location and the reason are returned; the submitted values are not echoed back.
    errors = [
        {"field": ".".join(str(part) for part in err.get("loc", ())), "message": err.get("msg", "Invalid value")}
        for err in exc.errors()
    ]
    return error_response(422, "VALIDATION_ERROR", "The request is not valid.", {"errors": errors})


async def _handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    # Details go only to the server log, never to the client (LLD §4.3, step 6).
    logger.exception("Unexpected error", exc_info=exc)
    return error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
