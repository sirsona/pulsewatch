"""Tests for the latest-sample endpoint and error envelope."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from tests.conftest import FakeRepository, StubCollector


class EchoPayload(BaseModel):
    count: int


def test_current_metrics_returns_latest_stored_sample(app: FastAPI, client: TestClient) -> None:
    repository = app.state.repository
    collector = app.state.collector
    assert isinstance(repository, FakeRepository)
    assert isinstance(collector, StubCollector)

    response = client.get("/api/v1/metrics/current")

    assert response.status_code == 200
    payload = response.json()
    assert payload["hostname"] == "test-host"
    assert payload["cpu"]["usage_percent"] == 12.5
    assert payload["memory"]["usage_percent"] == 50.0
    assert payload["disk"]["path"] == "/"
    assert payload["network"]["bytes_received"] == 2000
    assert payload["timestamp"] == "2026-01-15T12:00:00Z"
    assert repository.latest_calls == 1
    assert collector.call_count == 0


def test_current_metrics_returns_503_before_the_first_sample(
    app: FastAPI, client: TestClient
) -> None:
    repository = app.state.repository
    assert isinstance(repository, FakeRepository)
    repository.snapshot = None

    response = client.get("/api/v1/metrics/current", headers={"X-Request-ID": "empty-1"})

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["status"] == 503
    assert payload["code"] == "http_503"
    assert payload["title"] == "Service Unavailable"
    assert payload["detail"] == "No metrics samples are available yet."
    assert payload["request_id"] == "empty-1"


def test_current_metrics_returns_503_when_storage_fails(app: FastAPI, client: TestClient) -> None:
    app.state.repository = FakeRepository(healthy=False)

    response = client.get(
        "/api/v1/metrics/current",
        headers={"X-Request-ID": "storage-down-1"},
    )

    assert response.status_code == 503
    assert response.headers["X-Request-ID"] == "storage-down-1"
    payload = response.json()
    assert payload["status"] == 503
    assert payload["code"] == "http_503"
    assert payload["detail"] == "The metrics store is unavailable."
    assert payload["request_id"] == "storage-down-1"
    assert "simulated repository failure" not in payload["detail"]


def test_unhandled_errors_are_contained_by_the_middleware(app: FastAPI, client: TestClient) -> None:
    @app.get("/_test/boom")
    def boom() -> None:
        msg = "unhandled boom"
        raise RuntimeError(msg)

    response = client.get("/_test/boom", headers={"X-Request-ID": "boom-1"})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "boom-1"
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["code"] == "internal_server_error"
    assert payload["title"] == "Internal Server Error"
    assert payload["request_id"] == "boom-1"
    assert "unhandled boom" not in payload["detail"]


def test_not_found_uses_problem_details(client: TestClient) -> None:
    response = client.get("/does-not-exist", headers={"X-Request-ID": "missing-1"})

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["title"] == "Not Found"
    assert payload["status"] == 404
    assert payload["code"] == "http_404"
    assert payload["request_id"] == "missing-1"


def test_method_not_allowed_preserves_http_headers(client: TestClient) -> None:
    response = client.post("/health/live")

    assert response.status_code == 405
    assert response.headers["allow"] == "GET"
    assert response.json()["code"] == "http_405"


def test_validation_errors_have_field_details(app: FastAPI, client: TestClient) -> None:
    @app.post("/_test/validation")
    def validate(payload: EchoPayload) -> EchoPayload:
        return payload

    response = client.post("/_test/validation", json={"count": "not-an-integer"})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["code"] == "validation_error"
    assert payload["title"] == "Unprocessable Content"
    assert payload["errors"][0]["loc"] == ["body", "count"]


def test_openapi_documents_public_routes(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/v1/metrics/current" in schema["paths"]
    assert "/health/live" in schema["paths"]
    assert "/health/ready" in schema["paths"]
    assert "Metrics" in {tag["name"] for tag in schema["tags"]}
