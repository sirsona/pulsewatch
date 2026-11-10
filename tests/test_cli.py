"""Tests for the command-line wrapper around Uvicorn."""

from __future__ import annotations

from typing import Any

import pytest

from pulsewatch.__main__ import build_parser, main
from pulsewatch.core.config import Settings


def test_parser_defaults() -> None:
    args = build_parser().parse_args([])

    assert args.host is None
    assert args.port is None
    assert args.reload is False
    assert args.log_level is None


def test_main_propagates_overrides_to_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pre-register variables with monkeypatch so its teardown restores the
    # developer's environment even though main() writes them directly.
    for name in (
        "PULSEWATCH_HOST",
        "PULSEWATCH_PORT",
        "PULSEWATCH_LOG_LEVEL",
        "PULSEWATCH_ENVIRONMENT",
    ):
        monkeypatch.setenv(name, "original")

    calls: dict[str, Any] = {}

    def fake_run(app_path: str, **kwargs: Any) -> None:
        calls["app_path"] = app_path
        calls.update(kwargs)

    configured: list[Settings] = []
    monkeypatch.setattr("pulsewatch.__main__.uvicorn.run", fake_run)
    monkeypatch.setattr("pulsewatch.__main__.configure_logging", configured.append)

    main(
        [
            "--host",
            "0.0.0.0",
            "--port",
            "9100",
            "--log-level",
            "DEBUG",
            "--environment",
            "production",
            "--reload",
        ]
    )

    assert calls["app_path"] == "pulsewatch.main:app"
    assert calls["host"] == "0.0.0.0"
    assert calls["port"] == 9100
    assert calls["reload"] is True
    assert calls["log_config"] is None
    assert calls["access_log"] is False
    assert configured[0].environment == "production"
    assert configured[0].log_level == "DEBUG"


def test_invalid_log_level_exits() -> None:
    with pytest.raises(SystemExit):
        main(["--log-level", "VERBOSE"])
