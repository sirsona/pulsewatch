"""Shared fixtures for the PulseWatch test suite."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pulsewatch.api.schemas import (
    CPUMetrics,
    DiskMetrics,
    MemoryMetrics,
    NetworkMetrics,
    SystemSnapshot,
)
from pulsewatch.collectors.base import MetricsCollector
from pulsewatch.core.config import Settings, get_settings
from pulsewatch.main import create_app


def build_snapshot() -> SystemSnapshot:
    """Create a deterministic snapshot for route tests."""
    return SystemSnapshot(
        timestamp=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        hostname="test-host",
        platform="Linux-test",
        boot_time=datetime(2026, 1, 14, 12, 0, tzinfo=UTC),
        uptime_seconds=86_400.0,
        cpu=CPUMetrics(
            usage_percent=12.5,
            logical_cores=8,
            physical_cores=4,
            per_core_percent=[10.0, 15.0, 12.5, 11.0, 20.0, 8.0, 7.0, 16.5],
            load_average_1m=0.25,
            load_average_5m=0.5,
            load_average_15m=0.75,
        ),
        memory=MemoryMetrics(
            total_bytes=16_000_000_000,
            available_bytes=8_000_000_000,
            used_bytes=8_000_000_000,
            usage_percent=50.0,
            swap_total_bytes=2_000_000_000,
            swap_used_bytes=0,
            swap_usage_percent=0.0,
        ),
        disk=DiskMetrics(
            path="/",
            total_bytes=500_000_000_000,
            used_bytes=200_000_000_000,
            free_bytes=300_000_000_000,
            usage_percent=40.0,
            read_bytes=1_000_000,
            write_bytes=2_000_000,
            read_count=100,
            write_count=200,
        ),
        network=NetworkMetrics(
            bytes_sent=1_000,
            bytes_received=2_000,
            packets_sent=10,
            packets_received=20,
            errors_in=0,
            errors_out=0,
            drops_in=0,
            drops_out=0,
        ),
    )


class StubCollector(MetricsCollector):
    """Deterministic collector double with call accounting."""

    def __init__(self, snapshot: SystemSnapshot | None = None) -> None:
        self.snapshot = snapshot or build_snapshot()
        self.call_count = 0

    def collect(self) -> SystemSnapshot:
        self.call_count += 1
        return self.snapshot


class FailingCollector(MetricsCollector):
    """Collector double that simulates a psutil failure."""

    def collect(self) -> SystemSnapshot:
        msg = "simulated collector failure"
        raise RuntimeError(msg)


class FakeRepository:
    """In-memory repository double for route and sampler tests."""

    def __init__(
        self,
        snapshot: SystemSnapshot | None = None,
        *,
        healthy: bool = True,
    ) -> None:
        self.snapshot: SystemSnapshot | None = (
            snapshot if snapshot is not None else build_snapshot()
        )
        self.healthy = healthy
        self.saved: list[SystemSnapshot] = []
        self.latest_calls = 0
        self.connection_checks = 0

    async def save_snapshot(self, snapshot: SystemSnapshot) -> None:
        if not self.healthy:
            msg = "simulated repository failure"
            raise RuntimeError(msg)
        self.saved.append(snapshot)
        self.snapshot = snapshot

    async def latest_snapshot(self) -> SystemSnapshot | None:
        self.latest_calls += 1
        if not self.healthy:
            msg = "simulated repository failure"
            raise RuntimeError(msg)
        return self.snapshot

    async def check_connection(self) -> None:
        self.connection_checks += 1
        if not self.healthy:
            msg = "simulated repository failure"
            raise RuntimeError(msg)


class FakeSampler:
    """Readiness-only sampler double."""

    def __init__(self, *, healthy: bool) -> None:
        self.healthy = healthy

    def is_healthy(self, *, now: datetime | None = None) -> bool:
        return self.healthy


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    """Keep cached environment settings from leaking between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        disk_path=tmp_path,
        log_format="console",
        sampler_enabled=False,
    )


@pytest.fixture
def repository() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def app(settings: Settings, repository: FakeRepository) -> FastAPI:
    return create_app(
        settings=settings,
        collector=StubCollector(),
        repository=repository,
    )


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
