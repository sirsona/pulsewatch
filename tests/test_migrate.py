"""Tests for the packaged migration entrypoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from pulsewatch import migrate


def test_migration_scripts_are_available() -> None:
    scripts = migrate.migration_scripts_path()

    assert scripts.is_dir()
    assert (scripts / "env.py").is_file()
    assert (scripts / "versions" / "0001_metric_samples.py").is_file()


def test_build_config_points_at_packaged_migrations() -> None:
    config = migrate.build_config()

    script_location = config.get_main_option("script_location")
    assert script_location is not None
    assert Path(script_location) == migrate.migration_scripts_path()


def test_main_upgrades_to_head(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Config, str]] = []

    def fake_upgrade(config: Config, revision: str) -> None:
        calls.append((config, revision))

    monkeypatch.setattr(command, "upgrade", fake_upgrade)

    migrate.main()

    assert len(calls) == 1
    assert calls[0][1] == "head"
