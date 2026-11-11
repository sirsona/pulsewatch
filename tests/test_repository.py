"""Repository tests using an in-process SQLite database."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from pulsewatch.db.base import Base
from pulsewatch.db.database import Database
from pulsewatch.db.models import MetricSample
from pulsewatch.db.repository import SqlAlchemyMetricRepository
from tests.conftest import build_snapshot


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'metrics.db'}")
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield db
    await db.dispose()


async def test_latest_snapshot_is_none_on_an_empty_database(database: Database) -> None:
    repository = SqlAlchemyMetricRepository(database)

    assert await repository.latest_snapshot() is None


async def test_snapshot_round_trips_through_the_repository(database: Database) -> None:
    repository = SqlAlchemyMetricRepository(database)
    snapshot = build_snapshot()

    await repository.save_snapshot(snapshot)
    loaded = await repository.latest_snapshot()

    assert loaded == snapshot
    async with database.session_factory() as session:
        row = (await session.execute(select(MetricSample))).scalar_one()
    assert row.cpu_usage_percent == 12.5
    assert row.memory_usage_percent == 50.0
    assert row.disk_usage_percent == 40.0
    assert row.hostname == "test-host"
    assert row.payload["cpu"]["usage_percent"] == 12.5


async def test_latest_snapshot_is_ordered_by_collection_time(database: Database) -> None:
    repository = SqlAlchemyMetricRepository(database)
    older = build_snapshot()
    newer = build_snapshot().model_copy(
        update={
            "timestamp": older.timestamp + timedelta(seconds=15),
            "hostname": "newer-host",
        }
    )

    await repository.save_snapshot(newer)
    await repository.save_snapshot(older)
    loaded = await repository.latest_snapshot()

    assert loaded is not None
    assert loaded.hostname == "newer-host"


async def test_check_connection_on_a_reachable_database(database: Database) -> None:
    repository = SqlAlchemyMetricRepository(database)

    await repository.check_connection()
