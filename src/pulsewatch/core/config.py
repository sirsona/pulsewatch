"""Application settings loaded from the environment."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
Environment = Literal["development", "test", "production"]

_HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")

_DEFAULT_DATABASE_URL = "postgresql+asyncpg://pulsewatch:pulsewatch@127.0.0.1:5432/pulsewatch"


class Settings(BaseSettings):
    """Runtime configuration.

    Every value can be overridden with a ``PULSEWATCH_``-prefixed environment
    variable or an entry in ``.env``. See ``.env.example`` for the common set.
    """

    model_config = SettingsConfigDict(
        env_prefix="PULSEWATCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Environment = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65_535)
    log_level: LogLevel = "INFO"
    log_format: Literal["json", "console"] = "json"
    disk_path: Path = Path("/")
    request_id_header: str = "X-Request-ID"
    docs_enabled: bool = True
    database_url: SecretStr = SecretStr(_DEFAULT_DATABASE_URL)
    sampler_enabled: bool = True
    sample_interval_seconds: float = Field(default=15.0, ge=1.0, le=3600.0)
    sampler_stale_after_seconds: float = Field(default=45.0, ge=1.0, le=86_400.0)

    @field_validator("disk_path")
    @classmethod
    def validate_disk_path(cls, value: Path) -> Path:
        """Fail fast when the configured filesystem is not inspectable."""
        resolved = value.expanduser()
        if not resolved.exists():
            msg = f"disk_path does not exist: {resolved}"
            raise ValueError(msg)
        if not resolved.is_dir():
            msg = f"disk_path is not a directory: {resolved}"
            raise ValueError(msg)
        return resolved

    @field_validator("request_id_header")
    @classmethod
    def validate_request_id_header(cls, value: str) -> str:
        """Reject header names that could break response serialization."""
        if not _HEADER_NAME_PATTERN.fullmatch(value):
            msg = "request_id_header must be a valid HTTP header name"
            raise ValueError(msg)
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        """Require the async SQLAlchemy driver used by the application."""
        if not value.get_secret_value().startswith("postgresql+asyncpg://"):
            msg = "database_url must use the postgresql+asyncpg driver"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_sampling_window(self) -> Self:
        """A stale threshold below the interval would make readiness flap."""
        if self.sampler_stale_after_seconds < self.sample_interval_seconds:
            msg = "sampler_stale_after_seconds must be >= sample_interval_seconds"
            raise ValueError(msg)
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide settings instance."""
    return Settings()
