"""Tests for environment-driven configuration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from pulsewatch.core.config import Settings, get_settings


def clear_pulsewatch_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate settings tests from the developer's shell and project .env."""
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PULSEWATCH_"):
            monkeypatch.delenv(name, raising=False)


def test_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clear_pulsewatch_env(monkeypatch, tmp_path)

    settings = Settings()

    assert settings.environment == "development"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.log_level == "INFO"
    assert settings.log_format == "json"
    assert settings.docs_enabled is True
    assert settings.disk_path == Path("/")


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clear_pulsewatch_env(monkeypatch, tmp_path)
    monkeypatch.setenv("PULSEWATCH_ENVIRONMENT", "production")
    monkeypatch.setenv("PULSEWATCH_HOST", "0.0.0.0")
    monkeypatch.setenv("PULSEWATCH_PORT", "9000")
    monkeypatch.setenv("PULSEWATCH_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("PULSEWATCH_LOG_FORMAT", "console")
    monkeypatch.setenv("PULSEWATCH_DOCS_ENABLED", "false")
    monkeypatch.setenv("PULSEWATCH_DISK_PATH", str(tmp_path))

    settings = Settings()

    assert settings.environment == "production"
    assert settings.host == "0.0.0.0"
    assert settings.port == 9000
    assert settings.log_level == "DEBUG"
    assert settings.log_format == "console"
    assert settings.docs_enabled is False
    assert settings.disk_path == tmp_path


def test_dotenv_values_are_loaded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clear_pulsewatch_env(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text(
        "PULSEWATCH_ENVIRONMENT=test\nPULSEWATCH_PORT=8123\n",
        encoding="utf-8",
    )

    settings = Settings()

    assert settings.environment == "test"
    assert settings.port == 8123


def test_settings_are_cached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clear_pulsewatch_env(monkeypatch, tmp_path)
    monkeypatch.setenv("PULSEWATCH_PORT", "8124")

    first = get_settings()
    second = get_settings()
    assert first is second
    assert first.port == 8124

    get_settings.cache_clear()
    assert get_settings() is not first


@pytest.mark.parametrize("port", [0, 65_536, -1])
def test_invalid_port_is_rejected(port: int, tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(port=port, disk_path=tmp_path)


def test_missing_disk_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="does not exist"):
        Settings(disk_path=tmp_path / "missing")


def test_disk_path_must_be_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-directory"
    file_path.write_text("data", encoding="utf-8")

    with pytest.raises(ValidationError, match="not a directory"):
        Settings(disk_path=file_path)


def test_home_relative_disk_path_is_expanded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    settings = Settings(disk_path=Path("~"))

    assert settings.disk_path == tmp_path


@pytest.mark.parametrize(
    "header",
    ["", "X Request ID", "X-Request-ID\nInjected", "X-Request-ID:", "Bad/Header"],
)
def test_invalid_request_id_header_is_rejected(header: str, tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="request_id_header"):
        Settings(request_id_header=header, disk_path=tmp_path)


def test_custom_header_is_accepted(tmp_path: Path) -> None:
    settings = Settings(request_id_header="X-Correlation-ID", disk_path=tmp_path)

    assert settings.request_id_header == "X-Correlation-ID"
