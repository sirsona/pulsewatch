"""Metric sample persistence behind a small repository contract."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select, text

from pulsewatch.api.schemas import SystemSnapshot
from pulsewatch.db.database import Database
from pulsewatch.db.models import MetricSample


class MetricRepository(Protocol):
    """Storage operations required by the API and sampler."""

    async def save_snapshot(self, snapshot: SystemSnapshot) -> None:
        """Persist one snapshot."""
        ...

    async def latest_snapshot(self) -> SystemSnapshot | None:
        """Return the most recently collected snapshot, if any."""
        ...

    async def check_connection(self) -> None:
        """Raise when the database cannot serve a trivial query."""
        ...


class SqlAlchemyMetricRepository:
    """PostgreSQL-backed implementation of :class:`MetricRepository`."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def save_snapshot(self, snapshot: SystemSnapshot) -> None:
        record = MetricSample(
            collected_at=snapshot.timestamp,
            hostname=snapshot.hostname,
            cpu_usage_percent=snapshot.cpu.usage_percent,
            memory_usage_percent=snapshot.memory.usage_percent,
            disk_usage_percent=snapshot.disk.usage_percent,
            payload=snapshot.model_dump(mode="json"),
        )
        async with self._database.session_factory() as session:
            session.add(record)
            await session.commit()

    async def latest_snapshot(self) -> SystemSnapshot | None:
        statement = (
            select(MetricSample)
            .order_by(MetricSample.collected_at.desc(), MetricSample.id.desc())
            .limit(1)
        )
        async with self._database.session_factory() as session:
            record = (await session.execute(statement)).scalar_one_or_none()

        if record is None:
            return None
        return SystemSnapshot.model_validate(record.payload)

    async def check_connection(self) -> None:
        async with self._database.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
