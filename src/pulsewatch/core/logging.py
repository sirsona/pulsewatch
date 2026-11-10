"""Structured logging with request-scoped correlation IDs."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import IO, Any, Final

from pulsewatch.core.config import Settings

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

_EXTRA_FIELDS: Final[tuple[str, ...]] = (
    "event",
    "http_method",
    "path",
    "status_code",
    "duration_ms",
    "client_ip",
    "error_code",
)

logger = logging.getLogger("pulsewatch")


class JsonFormatter(logging.Formatter):
    """Render log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = request_id_ctx.get()
        if request_id is not None:
            payload["request_id"] = request_id

        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """Compact, human-readable output for local development."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).strftime("%H:%M:%S")
        line = f"{timestamp} {record.levelname:<8} {record.name:<24} {record.getMessage()}"
        request_id = request_id_ctx.get()
        if request_id is not None:
            line = f"{line} request_id={request_id}"
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


def configure_logging(settings: Settings, *, stream: IO[str] | None = None) -> None:
    """Configure the root logger and route Uvicorn logs through it."""
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter() if settings.log_format == "json" else ConsoleFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(settings.log_level)
    root.addHandler(handler)

    # Uvicorn installs its own handlers by default. Clearing them and enabling
    # propagation keeps server logs in the same structured format.
    for logger_name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(logging.NOTSET)

    # RequestContextMiddleware emits richer access logs (request ID, duration,
    # client IP). Uvicorn 0.54 enables its access logger whenever the logger
    # tree has a handler, so suppress the duplicate at the source.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.setLevel(logging.NOTSET)
