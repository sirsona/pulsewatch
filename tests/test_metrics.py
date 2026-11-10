"""Tests for the host metrics API and error envelope."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from tests.conftest import FailingCollector


class EchoPayload(BaseModel):
    count: int


def test_current_metrics_returns_snapshot(client: TestClient) -> None:
    response = client.get("/api/v1/metrics/current")

    assert response.status_code == 200
    payload = response.json()
    assert payload["hostname"] == "test-host"
    assert payload["cpu"]["usage_percent"] == 12.5
    assert payload["memory"]["usage_percent"] == 50.0
    assert payload["disk"]["path"] == "/"
    assert payload["network"]["bytes_received"] == 2000
    assert payload["timestamp"] == "2026-01-15T12:00:00Z"


def test_unhandled_collector_error_is_a_problem_details_response(
    app: FastAPI, client: TestClient
) -> None:
    app.state.collector = FailingCollector()

    response = client.get(
        "/api/v1/metrics/current",
        headers={"X-Request-ID": "error-request-1"},
    )

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "error-request-1"
    payload = response.json()
    assert payload["status"] == 500
    assert payload["code"] == "internal_server_error"
    assert payload["title"] == "Internal Server Error"
    assert payload["instance"] == "/api/v1/metrics/current"
    assert payload["request_id"] == "error-request-1"
    assert "simulated collector failure" not in payload["detail"]


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
