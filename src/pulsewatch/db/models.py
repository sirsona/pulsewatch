"""SQLAlchemy models for stored host metrics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from pulsewatch.db.base import Base

# SQLite is used only by the fast repository tests. Production always uses
# PostgreSQL, where the payload is stored as JSONB.
_JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
_ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class MetricSample(Base):
    """One persisted, point-in-time host snapshot."""

    __tablename__ = "metric_samples"

    id: Mapped[int] = mapped_column(_ID_TYPE, primary_key=True, autoincrement=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    cpu_usage_percent: Mapped[float] = mapped_column(Float, nullable=False)
    memory_usage_percent: Mapped[float] = mapped_column(Float, nullable=False)
    disk_usage_percent: Mapped[float] = mapped_column(Float, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(_JSON_TYPE, nullable=False)

    __table_args__ = (
        Index("ix_metric_samples_collected_at", "collected_at"),
        Index("ix_metric_samples_hostname_collected_at", "hostname", "collected_at"),
    )
