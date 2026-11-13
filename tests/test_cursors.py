"""Tests for opaque history pagination cursors."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from pulsewatch.api.cursors import HistoryWindow, decode_cursor, encode_cursor
from tests.conftest import stored_sample


def make_window(timestamp: datetime) -> HistoryWindow:
    return HistoryWindow(
        start=timestamp - timedelta(minutes=30),
        end=timestamp + timedelta(minutes=30),
    )


def test_cursor_round_trip() -> None:
    timestamp = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    sample = stored_sample(42, timestamp)
    window = make_window(timestamp)

    state = decode_cursor(encode_cursor(sample, window))

    assert state.collected_at == timestamp
    assert state.sample_id == 42
    assert state.window == window


def test_cursor_normalises_non_utc_offsets() -> None:
    offset = timezone(timedelta(hours=3))
    timestamp = datetime(2026, 1, 15, 15, 0, tzinfo=offset)
    sample = stored_sample(7, timestamp)
    window = HistoryWindow(
        start=datetime(2026, 1, 15, 14, 0, tzinfo=offset),
        end=datetime(2026, 1, 15, 16, 0, tzinfo=offset),
    )

    state = decode_cursor(encode_cursor(sample, window))

    assert state.collected_at == timestamp
    assert state.collected_at.utcoffset() == timedelta(0)
    assert state.window.start.utcoffset() == timedelta(0)
    assert state.window.end.utcoffset() == timedelta(0)
    assert state.sample_id == 7


def test_invalid_cursors_are_rejected() -> None:
    timestamp = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    valid = {
        "v": 2,
        "at": timestamp.isoformat(),
        "id": 1,
        "start": (timestamp - timedelta(minutes=30)).isoformat(),
        "end": (timestamp + timedelta(minutes=30)).isoformat(),
    }
    cursors = [
        "",
        "not-base64",
        "!!!!",
        base64.urlsafe_b64encode(b"not-json").decode(),
        base64.urlsafe_b64encode(json.dumps({**valid, "v": 1}).encode()).decode(),
        base64.urlsafe_b64encode(json.dumps({**valid, "id": 0}).encode()).decode(),
        base64.urlsafe_b64encode(json.dumps({**valid, "id": True}).encode()).decode(),
        base64.urlsafe_b64encode(
            json.dumps({**valid, "start": "2026-01-15T10:00:00"}).encode()
        ).decode(),
        base64.urlsafe_b64encode(json.dumps({**valid, "start": valid["end"]}).encode()).decode(),
        "a" * 513,
    ]

    for cursor in cursors:
        with pytest.raises(ValueError):
            decode_cursor(cursor)


def test_cursor_preserves_microseconds() -> None:
    timestamp = datetime(2026, 1, 15, 12, 0, 0, 123456, tzinfo=UTC)
    sample = stored_sample(1, timestamp)
    window = make_window(timestamp)

    state = decode_cursor(encode_cursor(sample, window))

    assert state.collected_at == timestamp
    assert state.collected_at.microsecond == 123456
