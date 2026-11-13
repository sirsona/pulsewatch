"""Apply Alembic migrations from an installed package."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def migration_scripts_path() -> Path:
    """Locate packaged migrations, falling back to a source checkout."""
    packaged = Path(__file__).resolve().parent / "migrations"
    if (packaged / "env.py").is_file():
        return packaged

    source_root = Path(__file__).resolve().parents[2] / "migrations"
    if (source_root / "env.py").is_file():
        return source_root

    msg = "PulseWatch migration scripts are missing from this installation"
    raise RuntimeError(msg)


def build_config() -> Config:
    """Build an Alembic config without relying on a working-directory ini file."""
    config = Config()
    config.set_main_option("script_location", str(migration_scripts_path()))
    return config


def main() -> None:
    """Upgrade the configured database to the latest schema revision."""
    command.upgrade(build_config(), "head")
