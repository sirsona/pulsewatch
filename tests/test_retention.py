"""Tests for batched retention cleanup and its lifecycle."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from pulsewatch.core.config import Settings
from pulsewatch.db.repository import StoredSample
from pulsewatch.main import create_app
from pulsewatch.services.retention import RetentionService
from tests.conftest import FakeRepository, StubCollector, stored_sample

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def records() -> list[StoredSample]:
    return [
        stored_sample(1, datetime(2026, 1, 1, 12, 0, tzinfo=UTC)),
        stored_sample(2, datetime(2026, 1, 2, 12, 0, tzinfo=UTC)),
        stored_sample(3, datetime(2026, 1, 14, 12, 0, tzinfo=UTC)),
    ]


def make_service(
    repository: FakeRepository,
    *,
    batch_size: int = 1000,
    interval_seconds: float = 3600,
) -> RetentionService:
    return RetentionService(
        repository,
        retention_days=7,
        interval_seconds=interval_seconds,
        batch_size=batch_size,
    )


async def test_cleanup_deletes_only_expired_samples() -> None:
    repository = FakeRepository()
    repository.records = records()
    service = make_service(repository)

    deleted = await service.cleanup_once(now=NOW)

    assert deleted == 2
    assert [record.id for record in repository.records] == [3]
    assert repository.delete_calls == 1


async def test_cleanup_uses_multiple_batches() -> None:
    repository = FakeRepository()
    repository.records = [
        *records(),
        stored_sample(4, datetime(2026, 1, 3, 12, 0, tzinfo=UTC)),
    ]
    service = make_service(repository, batch_size=2)

    deleted = await service.cleanup_once(now=NOW)

    assert deleted == 3
    assert repository.delete_calls == 2


async def test_cleanup_handles_no_expired_samples() -> None:
    repository = FakeRepository()
    repository.records = [records()[2]]
    service = make_service(repository)

    deleted = await service.cleanup_once(now=NOW)

    assert deleted == 0
    assert repository.delete_calls == 1


async def test_retention_loop_starts_and_stops() -> None:
    repository = FakeRepository()
    repository.records = records()
    service = make_service(repository, interval_seconds=0.01)

    service.start()
    try:
        for _ in range(100):
            if repository.delete_calls:
                break
            await asyncio.sleep(0.01)
        assert repository.delete_calls >= 1
        assert service.is_running
    finally:
        await service.stop()

    assert service.is_running is False


async def test_retention_loop_survives_database_failures() -> None:
    repository = FakeRepository(healthy=False)
    service = make_service(repository, interval_seconds=0.01)

    service.start()
    try:
        for _ in range(100):
            if repository.delete_calls:
                break
            await asyncio.sleep(0.01)
        assert repository.delete_calls >= 1
        assert service.is_running
    finally:
        await service.stop()

    assert service.is_running is False


def test_application_lifespan_starts_and_stops_retention(tmp_path: Path) -> None:
    repository = FakeRepository()
    repository.records = records()
    settings = Settings(
        environment="test",
        disk_path=tmp_path,
        log_format="console",
        sampler_enabled=False,
        retention_enabled=True,
        retention_days=7,
        retention_cleanup_interval_seconds=3600,
        retention_batch_size=1000,
    )
    app = create_app(
        settings=settings,
        collector=StubCollector(),
        repository=repository,
    )

    with TestClient(app):
        for _ in range(100):
            if repository.delete_calls:
                break
            time.sleep(0.01)
        assert app.state.retention.is_running

    assert app.state.retention.is_running is False
    assert repository.delete_calls >= 1
