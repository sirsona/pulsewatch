"""PostgreSQL integration tests for the repository and migration schema."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

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
