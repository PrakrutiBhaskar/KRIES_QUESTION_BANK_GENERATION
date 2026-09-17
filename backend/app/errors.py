"""
Error contract.

api-contract.md says *every* endpoint returns errors as:

    {"error": "string", "detail": "string"}

FastAPI's default is `{"detail": ...}`, and its 422 for request-body
validation is a list of objects — neither matches. The handlers here
normalise all three sources (our own APIError, FastAPI's HTTPException,
pydantic's RequestValidationError, and anything uncaught) into that one
shape, so the frontend has exactly one error parser to write.

Module A's exceptions map onto these per exceptions.py:
    InvalidRequestError       -> 400 invalid_request
    GroqAPIError              -> 502 groq_api_error
    GenerationValidationError -> 422 validation_failed
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("backend.errors")


class APIError(Exception):
    """Base for errors the API raises deliberately."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error: str = "internal_error"

    def __init__(self, detail: str, *, error: str | None = None):
        self.detail = detail
        if error:
            self.error = error
        super().__init__(detail)


class BadRequestError(APIError):
    status_code = status.HTTP_400_BAD_REQUEST
    error = "invalid_request"


class NotFoundError(APIError):
    status_code = status.HTTP_404_NOT_FOUND
    error = "not_found"


class ConflictError(APIError):
    status_code = status.HTTP_409_CONFLICT
    error = "conflict"


class UnprocessableError(APIError):
    # Written as a literal rather than status.HTTP_422_* — Starlette renamed
    # that constant and the old spelling emits a deprecation warning.
    status_code = 422
    error = "validation_failed"


class UpstreamError(APIError):
    status_code = status.HTTP_502_BAD_GATEWAY
    error = "upstream_error"


class ServiceUnavailableError(APIError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error = "service_unavailable"


def error_response(status_code: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": error, "detail": detail}
    )


def _flatten_validation_errors(exc: RequestValidationError) -> str:
    """Turn pydantic's structured errors into one readable sentence."""
    parts: list[str] = []
    for err in exc.errors():
        # loc is like ("body", "count") — drop the source segment.
        loc = ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query"))
        msg = err.get("msg", "invalid value")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) or "request validation failed"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError):
        return error_response(exc.status_code, exc.error, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        # A malformed request body is the caller's fault, so this is a 400
        # per api-contract.md's "invalid ... combination" case — not FastAPI's
        # default 422, which the contract reserves for generated output that
        # failed validation.
        return error_response(
            status.HTTP_400_BAD_REQUEST,
            "invalid_request",
            _flatten_validation_errors(exc),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict):  # already in contract shape
            return error_response(
                exc.status_code,
                str(detail.get("error", "error")),
                str(detail.get("detail", "")),
            )
        return error_response(exc.status_code, _slug(exc.status_code), str(detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "An unexpected error occurred.",
        )


def _slug(status_code: int) -> str:
    return {
        400: "invalid_request",
        404: "not_found",
        409: "conflict",
        422: "validation_failed",
        502: "upstream_error",
        503: "service_unavailable",
    }.get(status_code, "error")
