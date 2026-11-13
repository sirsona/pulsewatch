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


async def test_history_query_is_newest_first_and_time_bounded(
    database: Database,
) -> None:
    repository = SqlAlchemyMetricRepository(database)
    base = build_snapshot()
    older = base.model_copy(update={"timestamp": base.timestamp - timedelta(seconds=20)})
    middle = base.model_copy(update={"timestamp": base.timestamp - timedelta(seconds=10)})
    newer = base

    for snapshot in (older, middle, newer):
        await repository.save_snapshot(snapshot)

    page = await repository.list_snapshots(
        start=older.timestamp,
        end=newer.timestamp,
        limit=2,
    )

    assert [record.snapshot.timestamp for record in page] == [
        newer.timestamp,
        middle.timestamp,
    ]

    next_page = await repository.list_snapshots(
        start=older.timestamp,
        end=newer.timestamp,
        limit=2,
        before=(page[-1].snapshot.timestamp, page[-1].id),
    )

    assert [record.snapshot.timestamp for record in next_page] == [older.timestamp]


async def test_history_bounds_include_both_endpoints(database: Database) -> None:
    repository = SqlAlchemyMetricRepository(database)
    snapshot = build_snapshot()
    await repository.save_snapshot(snapshot)

    page = await repository.list_snapshots(
        start=snapshot.timestamp,
        end=snapshot.timestamp,
        limit=10,
    )

    assert len(page) == 1
    assert page[0].snapshot == snapshot


async def test_delete_samples_before_cutoff(database: Database) -> None:
    repository = SqlAlchemyMetricRepository(database)
    snapshot = build_snapshot()
    old = snapshot.model_copy(update={"timestamp": snapshot.timestamp - timedelta(days=10)})
    await repository.save_snapshot(old)
    await repository.save_snapshot(snapshot)

    deleted = await repository.delete_samples_before(
        snapshot.timestamp - timedelta(days=7),
        batch_size=100,
    )

    assert deleted == 1
    remaining = await repository.list_snapshots(
        start=old.timestamp,
        end=snapshot.timestamp,
        limit=10,
    )
    assert [record.snapshot for record in remaining] == [snapshot]


async def test_same_timestamp_orders_by_row_identity(database: Database) -> None:
    repository = SqlAlchemyMetricRepository(database)
    snapshot = build_snapshot()
    first = snapshot.model_copy(update={"hostname": "first"})
    second = snapshot.model_copy(update={"hostname": "second"})
    await repository.save_snapshot(first)
    await repository.save_snapshot(second)

    page = await repository.list_snapshots(
        start=snapshot.timestamp,
        end=snapshot.timestamp,
        limit=1,
    )

    assert page[0].snapshot.hostname == "second"
    next_page = await repository.list_snapshots(
        start=snapshot.timestamp,
        end=snapshot.timestamp,
        limit=1,
        before=(page[0].snapshot.timestamp, page[0].id),
    )
    assert next_page[0].snapshot.hostname == "first"


class TimeoutDatabase:
    """A database double whose session factory raises a network timeout."""

    def session_factory(self) -> None:
        raise TimeoutError("simulated connection timeout")


async def test_network_timeouts_are_translated_to_storage_errors() -> None:
    from typing import cast

    from pulsewatch.db.database import Database
    from pulsewatch.db.errors import StorageUnavailableError
    from pulsewatch.db.repository import SqlAlchemyMetricRepository

    repository = SqlAlchemyMetricRepository(cast(Database, TimeoutDatabase()))

    with pytest.raises(StorageUnavailableError):
        await repository.latest_snapshot()
