"""RFC 9457 problem-details responses and exception handlers."""

from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ExceptionHandler

from pulsewatch.core.logging import request_id_ctx

PROBLEM_MEDIA_TYPE = "application/problem+json"


def problem_response(
    request: Request,
    *,
    status: int,
    title: str,
    detail: str,
    error_code: str,
    errors: list[dict[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build a consistent, machine-readable error response."""
    payload: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "code": error_code,
    }

    request_id = request_id_ctx.get()
    if request_id is not None:
        payload["request_id"] = request_id
    if errors is not None:
        payload["errors"] = errors

    return JSONResponse(
        status_code=status,
        content=payload,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def _reason_phrase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:  # pragma: no cover - defensive for non-standard status codes
        return "Request failed"


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Render framework HTTP errors as problem details."""
    detail = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
    return problem_response(
        request,
        status=exc.status_code,
        title=_reason_phrase(exc.status_code),
        detail=detail,
        error_code=f"http_{exc.status_code}",
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Expose field-level validation errors without leaking internals."""
    return problem_response(
        request,
        status=422,
        title="Unprocessable Content",
        detail="The request payload failed validation.",
        error_code="validation_error",
        errors=jsonable_encoder(exc.errors()),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the application-wide HTTP error handlers."""
    app.add_exception_handler(
        StarletteHTTPException,
        cast(ExceptionHandler, http_exception_handler),
    )
    app.add_exception_handler(
        RequestValidationError,
        cast(ExceptionHandler, validation_exception_handler),
    )
