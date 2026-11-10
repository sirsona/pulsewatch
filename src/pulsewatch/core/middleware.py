"""HTTP request correlation and access logging middleware."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from pulsewatch.core.errors import problem_response
from pulsewatch.core.logging import logger, request_id_ctx

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _resolve_request_id(candidate: str | None) -> str:
    """Reuse a safe caller-supplied ID, otherwise generate a new one."""
    if candidate is not None and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request ID, log each request, and contain unhandled errors."""

    def __init__(self, app: ASGIApp, *, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = _resolve_request_id(request.headers.get(self.header_name))
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        status_code = 500

        access_context = {
            "http_method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else None,
        }

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[self.header_name] = request_id
            return response
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "request failed",
                extra={
                    **access_context,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "error_code": "internal_server_error",
                },
            )
            response = problem_response(
                request,
                status=500,
                title="Internal Server Error",
                detail="An unexpected error occurred while processing the request.",
                error_code="internal_server_error",
            )
            response.headers[self.header_name] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "request completed",
                extra={
                    **access_context,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            request_id_ctx.reset(token)
