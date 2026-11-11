"""Tests for the background sampling service."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pulsewatch.api.schemas import SystemSnapshot
from pulsewatch.services.sampler import SamplerService
from tests.conftest import FakeRepository, StubCollector


class FailingSaveRepository(FakeRepository):
    """Repository double whose writes always fail."""

    async def save_snapshot(self, snapshot: SystemSnapshot) -> None:
        msg = "simulated write failure"
        raise RuntimeError(msg)


def make_sampler(
    repository: FakeRepository,
    *,
    interval_seconds: float = 15.0,
    stale_after_seconds: float = 45.0,
) -> tuple[SamplerService, StubCollector]:
    collector = StubCollector()
    sampler = SamplerService(
        collector,
        repository,
        interval_seconds=interval_seconds,
        stale_after_seconds=stale_after_seconds,
    )
    return sampler, collector


async def test_sample_once_persists_and_marks_the_sampler_healthy() -> None:
    repository = FakeRepository()
    sampler, collector = make_sampler(repository)
    before = datetime.now(UTC)

    snapshot = await sampler.sample_once()

    assert repository.saved == [snapshot]
    assert collector.call_count == 1
    assert sampler.last_success_at is not None
    assert sampler.last_success_at >= before
    assert sampler.is_healthy()
    assert not sampler.is_running


async def test_a_failed_write_does_not_mark_the_sampler_healthy() -> None:
    sampler, _ = make_sampler(FailingSaveRepository())

    try:
        await sampler.sample_once()
    except RuntimeError as exc:
        assert str(exc) == "simulated write failure"
    else:  # pragma: no cover - assertion helper
        raise AssertionError("sample_once should propagate repository failures")

    assert sampler.last_success_at is None
    assert sampler.is_healthy() is False


async def test_freshness_expires_after_the_configured_window() -> None:
    repository = FakeRepository()
    sampler, _ = make_sampler(repository, stale_after_seconds=45)
    await sampler.sample_once()

    later = datetime.now(UTC) + timedelta(seconds=46)

    assert sampler.is_healthy(now=later) is False


async def test_start_and_stop_run_the_background_loop() -> None:
    repository = FakeRepository()
    sampler, _ = make_sampler(repository, interval_seconds=0.01, stale_after_seconds=1)

    sampler.start()
    try:
        for _ in range(100):
            if repository.saved:
                break
            await asyncio.sleep(0.01)
        assert repository.saved
        assert sampler.is_running
    finally:
        await sampler.stop()

    assert sampler.is_running is False


async def test_stop_is_safe_when_the_sampler_was_never_started() -> None:
    sampler, _ = make_sampler(FakeRepository())

    await sampler.stop()

    assert sampler.is_running is False


def test_application_lifespan_runs_and_stops_the_sampler(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from pulsewatch.core.config import Settings
    from pulsewatch.main import create_app

    repository = FakeRepository()
    settings = Settings(
        environment="test",
        disk_path=tmp_path,
        log_format="console",
        sampler_enabled=True,
        sample_interval_seconds=1,
        sampler_stale_after_seconds=5,
    )
    app = create_app(
        settings=settings,
        collector=StubCollector(),
        repository=repository,
    )

    with TestClient(app) as client:
        for _ in range(100):
            if repository.saved:
                break
            time.sleep(0.01)
        response = client.get("/health/ready")
        assert app.state.sampler.is_running

    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok", "sampler": "ok"}
    assert app.state.sampler.is_running is False
