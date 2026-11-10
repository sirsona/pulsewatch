"""Tests for JSON/console log formatting and request context."""

from __future__ import annotations

import io
import json
import logging
import sys
from collections.abc import Iterator
from types import TracebackType

import pytest

from pulsewatch.core.config import Settings
from pulsewatch.core.logging import (
    ConsoleFormatter,
    JsonFormatter,
    configure_logging,
    request_id_ctx,
)


@pytest.fixture(autouse=True)
def reset_request_id() -> Iterator[None]:
    token = request_id_ctx.set(None)
    yield
    request_id_ctx.reset(token)


ExcInfo = tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None]


def make_record(
    message: str = "hello %s",
    args: tuple[object, ...] = ("world",),
    *,
    level: int = logging.INFO,
    exc_info: ExcInfo | None = None,
) -> logging.LogRecord:
    return logging.LogRecord(
        name="pulsewatch.test",
        level=level,
        pathname=__file__,
        lineno=42,
        msg=message,
        args=args,
        exc_info=exc_info,
    )


def test_json_formatter_emits_structured_record() -> None:
    request_id_ctx.set("req-123")
    record = make_record(level=logging.WARNING)
    record.event = "test_event"
    record.status_code = 418

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "warning"
    assert payload["logger"] == "pulsewatch.test"
    assert payload["message"] == "hello world"
    assert payload["request_id"] == "req-123"
    assert payload["event"] == "test_event"
    assert payload["status_code"] == 418
    assert payload["timestamp"].endswith("+00:00")


def test_json_formatter_omits_absent_request_id() -> None:
    payload = json.loads(JsonFormatter().format(make_record()))

    assert "request_id" not in payload


def test_json_formatter_includes_traceback() -> None:
    try:
        raise ValueError("bad value")
    except ValueError:
        exc_info = sys.exc_info()

    payload = json.loads(JsonFormatter().format(make_record(exc_info=exc_info)))

    assert "ValueError: bad value" in payload["exception"]


def test_console_formatter_is_human_readable() -> None:
    request_id_ctx.set("req-456")
    output = ConsoleFormatter().format(make_record())

    assert "hello world" in output
    assert "INFO" in output
    assert "request_id=req-456" in output
    assert not output.startswith("{")


def test_console_formatter_without_request_id() -> None:
    output = ConsoleFormatter().format(make_record())

    assert "request_id" not in output


def test_console_formatter_includes_traceback() -> None:
    try:
        raise RuntimeError("console boom")
    except RuntimeError:
        exc_info = sys.exc_info()

    output = ConsoleFormatter().format(make_record(exc_info=exc_info))

    assert "RuntimeError: console boom" in output


@pytest.mark.parametrize("log_format", ["json", "console"])
def test_configure_logging_routes_root_logs(log_format: str) -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    buffer = io.StringIO()
    settings = Settings(environment="test", log_format=log_format, log_level="DEBUG")

    try:
        configure_logging(settings, stream=buffer)
        logging.getLogger("pulsewatch.test").info("configured")
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)

    output = buffer.getvalue().strip()
    assert output
    if log_format == "json":
        assert json.loads(output)["message"] == "configured"
    else:
        assert "configured" in output


def test_configure_logging_reconfigures_uvicorn() -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    settings = Settings(environment="test", log_format="json")
    access_logger = logging.getLogger("uvicorn.access")
    error_logger = logging.getLogger("uvicorn.error")
    original_access_handlers = access_logger.handlers[:]
    original_access_propagate = access_logger.propagate
    original_access_level = access_logger.level
    original_error_handlers = error_logger.handlers[:]
    original_error_propagate = error_logger.propagate
    original_error_level = error_logger.level
    access_logger.addHandler(logging.NullHandler())
    error_logger.propagate = False

    try:
        configure_logging(settings, stream=io.StringIO())

        # Middleware access logs replace Uvicorn's duplicate access line.
        assert access_logger.propagate is False
        assert access_logger.handlers == []
        # Server errors still flow into the structured root handler.
        assert error_logger.propagate is True
        assert error_logger.handlers == []
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)
        access_logger.handlers = original_access_handlers
        access_logger.propagate = original_access_propagate
        access_logger.setLevel(original_access_level)
        error_logger.handlers = original_error_handlers
        error_logger.propagate = original_error_propagate
        error_logger.setLevel(original_error_level)
