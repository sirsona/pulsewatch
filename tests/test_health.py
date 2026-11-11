"""Tests for service discovery and health endpoints."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pulsewatch import __version__
from pulsewatch.collectors.base import MetricsCollector
from pulsewatch.core.config import Settings
from pulsewatch.main import create_app
from tests.conftest import (
    FakeRepository,
    FakeSampler,
    StubCollector,
    build_snapshot,
)


def test_root_returns_service_metadata(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "pulsewatch"
    assert payload["version"] == __version__
    assert payload["environment"] == "test"
    assert payload["documentation"] == "/docs"
    assert payload["health"] == {"live": "/health/live", "ready": "/health/ready"}


def test_liveness_does_not_collect_metrics(app: FastAPI, client: TestClient) -> None:
    collector = app.state.collector
    assert isinstance(collector, StubCollector)

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert collector.call_count == 0


def test_readiness_checks_the_database_without_collecting_psutil(
    app: FastAPI, client: TestClient
) -> None:
    repository = app.state.repository
    collector = app.state.collector
    assert isinstance(repository, FakeRepository)
    assert isinstance(collector, StubCollector)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok", "sampler": "disabled"}
    assert repository.connection_checks == 1
    assert collector.call_count == 0


def test_readiness_is_degraded_when_the_database_is_unavailable(
    app: FastAPI, client: TestClient
) -> None:
    app.state.repository = FakeRepository(healthy=False)

    response = client.get("/health/ready", headers={"X-Request-ID": "db-down-1"})

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["checks"] == {"database": "unavailable", "sampler": "disabled"}
    assert response.headers["X-Request-ID"] == "db-down-1"


def test_readiness_is_degraded_when_the_sampler_is_stale(app: FastAPI, client: TestClient) -> None:
    app.state.settings = app.state.settings.model_copy(update={"sampler_enabled": True})
    app.state.sampler = FakeSampler(healthy=False)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"] == {"database": "ok", "sampler": "stale"}


def test_readiness_is_ok_when_the_sampler_is_fresh(app: FastAPI, client: TestClient) -> None:
    app.state.settings = app.state.settings.model_copy(update={"sampler_enabled": True})
    app.state.sampler = FakeSampler(healthy=True)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok", "sampler": "ok"}


def test_docs_can_be_disabled(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        disk_path=tmp_path,
        docs_enabled=False,
        log_format="console",
        sampler_enabled=False,
    )
    app = create_app(
        settings=settings,
        collector=StubCollector(build_snapshot()),
        repository=FakeRepository(),
    )

    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/").json()["documentation"] is None


def test_supplied_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "test-request-123"})

    assert response.headers["X-Request-ID"] == "test-request-123"


def test_unsafe_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "not a valid id"})

    generated = response.headers["X-Request-ID"]
    assert generated != "not a valid id"
    assert re.fullmatch(r"[0-9a-f]{32}", generated)


def test_custom_request_id_header(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        disk_path=tmp_path,
        request_id_header="X-Correlation-ID",
        log_format="console",
        sampler_enabled=False,
    )
    app = create_app(
        settings=settings,
        collector=StubCollector(),
        repository=FakeRepository(),
    )

    with TestClient(app) as client:
        response = client.get("/health/live", headers={"X-Correlation-ID": "corr-42"})

    assert response.headers["X-Correlation-ID"] == "corr-42"
    assert "X-Request-ID" not in response.headers


def test_collector_protocol_is_runtime_usable() -> None:
    collector: MetricsCollector = StubCollector()

    assert collector.collect().hostname == "test-host"
