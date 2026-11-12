"""Tests for the bounded, paginated metric history endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pulsewatch.db.repository import StoredSample
from tests.conftest import FakeRepository, stored_sample

BASE = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
WINDOW = {
    "start": (BASE - timedelta(seconds=1)).isoformat(),
    "end": (BASE + timedelta(seconds=31)).isoformat(),
}


def history_records() -> list[StoredSample]:
    return [
        stored_sample(1, BASE),
        stored_sample(2, BASE + timedelta(seconds=10)),
        stored_sample(3, BASE + timedelta(seconds=20)),
    ]


def test_history_returns_newest_first_page(app: FastAPI, client: TestClient) -> None:
    repository = app.state.repository
    assert isinstance(repository, FakeRepository)
    repository.records = history_records()

    response = client.get(
        "/api/v1/metrics/history",
        params={**WINDOW, "limit": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["limit"] == 2
    assert payload["next_cursor"]
    assert [sample["timestamp"] for sample in payload["samples"]] == [
        "2026-01-15T12:00:20Z",
        "2026-01-15T12:00:10Z",
    ]
    assert repository.history_calls == 1


def test_history_cursor_returns_the_next_page(app: FastAPI, client: TestClient) -> None:
    repository = app.state.repository
    assert isinstance(repository, FakeRepository)
    repository.records = history_records()

    first = client.get(
        "/api/v1/metrics/history",
        params={**WINDOW, "limit": 2},
    ).json()
    second = client.get(
        "/api/v1/metrics/history",
        params={
            **WINDOW,
            "limit": 2,
            "cursor": first["next_cursor"],
        },
    )

    assert second.status_code == 200
    payload = second.json()
    assert payload["count"] == 1
    assert payload["next_cursor"] is None
    assert payload["samples"][0]["timestamp"] == "2026-01-15T12:00:00Z"


def test_history_bounds_are_inclusive(app: FastAPI, client: TestClient) -> None:
    repository = app.state.repository
    assert isinstance(repository, FakeRepository)
    repository.records = history_records()

    response = client.get(
        "/api/v1/metrics/history",
        params={
            "start": BASE.isoformat(),
            "end": (BASE + timedelta(seconds=10)).isoformat(),
            "limit": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["next_cursor"] is None


def test_history_defaults_to_the_last_hour(app: FastAPI, client: TestClient) -> None:
    repository = app.state.repository
    assert isinstance(repository, FakeRepository)
    repository.records = history_records()

    response = client.get("/api/v1/metrics/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 0
    start = datetime.fromisoformat(payload["start"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(payload["end"].replace("Z", "+00:00"))
    assert end - start == timedelta(hours=1)


def test_history_empty_range(app: FastAPI, client: TestClient) -> None:
    repository = app.state.repository
    assert isinstance(repository, FakeRepository)
    repository.records = history_records()

    response = client.get(
        "/api/v1/metrics/history",
        params={
            "start": "2025-01-01T00:00:00+00:00",
            "end": "2025-01-02T00:00:00+00:00",
        },
    )

    assert response.status_code == 200
    assert response.json()["count"] == 0
    assert response.json()["next_cursor"] is None


def test_history_rejects_naive_timestamps(client: TestClient) -> None:
    response = client.get(
        "/api/v1/metrics/history",
        params={
            "start": "2026-01-15T12:00:00",
            "end": "2026-01-15T13:00:00",
        },
    )

    assert response.status_code == 422
    assert "timezone" in response.json()["detail"]


def test_history_rejects_reversed_ranges(client: TestClient) -> None:
    response = client.get(
        "/api/v1/metrics/history",
        params={
            "start": "2026-01-15T13:00:00+00:00",
            "end": "2026-01-15T12:00:00+00:00",
        },
    )

    assert response.status_code == 422
    assert "earlier" in response.json()["detail"]


def test_history_rejects_ranges_longer_than_seven_days(client: TestClient) -> None:
    response = client.get(
        "/api/v1/metrics/history",
        params={
            "start": "2026-01-01T00:00:00+00:00",
            "end": "2026-01-09T00:00:00+00:00",
        },
    )

    assert response.status_code == 422
    assert "7 days" in response.json()["detail"]


def test_history_rejects_invalid_cursors(client: TestClient) -> None:
    response = client.get(
        "/api/v1/metrics/history",
        params={**WINDOW, "cursor": "not-a-cursor"},
    )

    assert response.status_code == 422
    assert "cursor" in response.json()["detail"]


def test_history_rejects_invalid_limits(client: TestClient) -> None:
    for limit in (0, 1001):
        response = client.get(
            "/api/v1/metrics/history",
            params={**WINDOW, "limit": limit},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"


def test_history_returns_503_when_storage_fails(app: FastAPI, client: TestClient) -> None:
    app.state.repository = FakeRepository(healthy=False)

    response = client.get(
        "/api/v1/metrics/history",
        params=WINDOW,
        headers={"X-Request-ID": "history-down-1"},
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["detail"] == "The metrics store is unavailable."
    assert payload["request_id"] == "history-down-1"
    assert "simulated repository failure" not in payload["detail"]
