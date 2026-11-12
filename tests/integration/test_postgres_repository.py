"""PostgreSQL integration tests for the repository and migration schema."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy import delete

from pulsewatch.db.database import Database
from pulsewatch.db.models import MetricSample
from pulsewatch.db.repository import SqlAlchemyMetricRepository
from tests.conftest import build_snapshot

TEST_DATABASE_URL = os.getenv("PULSEWATCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        TEST_DATABASE_URL is None,
        reason="PULSEWATCH_TEST_DATABASE_URL is not configured",
    ),
]


@pytest.fixture
async def database() -> AsyncIterator[Database]:
    assert TEST_DATABASE_URL is not None
    db = Database(TEST_DATABASE_URL)
    async with db.engine.begin() as connection:
        await connection.execute(delete(MetricSample))
    yield db
    async with db.engine.begin() as connection:
        await connection.execute(delete(MetricSample))
    await db.dispose()


async def test_postgresql_repository_round_trip(database: Database) -> None:
    """The migrated PostgreSQL table accepts and returns a full snapshot."""
    repository = SqlAlchemyMetricRepository(database)
    snapshot = build_snapshot()

    await repository.save_snapshot(snapshot)
    loaded = await repository.latest_snapshot()

    assert loaded == snapshot
    await repository.check_connection()


async def test_postgresql_history_and_retention(database: Database) -> None:
    """History pagination and retention work against the migrated table."""
    repository = SqlAlchemyMetricRepository(database)
    base = build_snapshot()
    older = base.model_copy(update={"timestamp": base.timestamp - timedelta(seconds=20)})
    newer = base
    for snapshot in (older, newer):
        await repository.save_snapshot(snapshot)

    page = await repository.list_snapshots(
        start=older.timestamp,
        end=newer.timestamp,
        limit=1,
    )
    assert len(page) == 1
    assert page[0].snapshot == newer

    next_page = await repository.list_snapshots(
        start=older.timestamp,
        end=newer.timestamp,
        limit=1,
        before=(page[0].snapshot.timestamp, page[0].id),
    )
    assert len(next_page) == 1
    assert next_page[0].snapshot == older

    cutoff = newer.timestamp + timedelta(seconds=1)
    first_delete = await repository.delete_samples_before(cutoff, batch_size=1)
    second_delete = await repository.delete_samples_before(cutoff, batch_size=1)
    assert (first_delete, second_delete) == (1, 1)
    assert await repository.latest_snapshot() is None
