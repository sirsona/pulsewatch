"""Metric sample persistence behind a small repository contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast

from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.engine import CursorResult

from pulsewatch.api.schemas import SystemSnapshot
from pulsewatch.db.database import Database
from pulsewatch.db.models import MetricSample


@dataclass(frozen=True, slots=True)
class StoredSample:
    """A persisted snapshot together with its database identity."""

    id: int
    snapshot: SystemSnapshot


class MetricRepository(Protocol):
    """Storage operations required by the API, sampler, and retention job."""

    async def save_snapshot(self, snapshot: SystemSnapshot) -> None:
        """Persist one snapshot."""
        ...

    async def latest_snapshot(self) -> SystemSnapshot | None:
        """Return the most recently collected snapshot, if any."""
        ...

    async def list_snapshots(
        self,
        *,
        start: datetime,
        end: datetime,
        limit: int,
        before: tuple[datetime, int] | None = None,
    ) -> list[StoredSample]:
        """Return a descending page of samples within an inclusive range."""
        ...

    async def delete_samples_before(self, cutoff: datetime, *, batch_size: int) -> int:
        """Delete one batch of samples collected before the cutoff."""
        ...

    async def check_connection(self) -> None:
        """Raise when the database cannot serve a trivial query."""
        ...


class SqlAlchemyMetricRepository:
    """PostgreSQL-backed implementation of :class:`MetricRepository`."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def _stored(record: MetricSample) -> StoredSample:
        return StoredSample(
            id=record.id,
            snapshot=SystemSnapshot.model_validate(record.payload),
        )

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
        return self._stored(record).snapshot

    async def list_snapshots(
        self,
        *,
        start: datetime,
        end: datetime,
        limit: int,
        before: tuple[datetime, int] | None = None,
    ) -> list[StoredSample]:
        filters = [
            MetricSample.collected_at >= start,
            MetricSample.collected_at <= end,
        ]
        if before is not None:
            before_time, before_id = before
            filters.append(
                or_(
                    MetricSample.collected_at < before_time,
                    and_(
                        MetricSample.collected_at == before_time,
                        MetricSample.id < before_id,
                    ),
                )
            )

        statement = (
            select(MetricSample)
            .where(*filters)
            .order_by(MetricSample.collected_at.desc(), MetricSample.id.desc())
            .limit(limit)
        )
        async with self._database.session_factory() as session:
            records = (await session.execute(statement)).scalars().all()

        return [self._stored(record) for record in records]

    async def delete_samples_before(self, cutoff: datetime, *, batch_size: int) -> int:
        batch = (
            select(MetricSample.id)
            .where(MetricSample.collected_at < cutoff)
            .order_by(MetricSample.collected_at.asc(), MetricSample.id.asc())
            .limit(batch_size)
            .scalar_subquery()
        )
        statement = delete(MetricSample).where(MetricSample.id.in_(batch))
        async with self._database.session_factory() as session:
            result = cast(CursorResult[Any], await session.execute(statement))
            await session.commit()

        return max(result.rowcount or 0, 0)

    async def check_connection(self) -> None:
        async with self._database.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
