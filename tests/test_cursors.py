"""Tests for opaque history pagination cursors."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from pulsewatch.api.cursors import decode_cursor, encode_cursor
from tests.conftest import stored_sample


def test_cursor_round_trip() -> None:
    timestamp = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    sample = stored_sample(42, timestamp)

    cursor = encode_cursor(sample)
    decoded_time, decoded_id = decode_cursor(cursor)

    assert decoded_time == timestamp
    assert decoded_id == 42


def test_cursor_normalises_non_utc_offsets() -> None:
    offset = timezone(timedelta(hours=3))
    timestamp = datetime(2026, 1, 15, 15, 0, tzinfo=offset)
    sample = stored_sample(7, timestamp)

    decoded_time, decoded_id = decode_cursor(encode_cursor(sample))

    assert decoded_time == timestamp
    assert decoded_time.utcoffset() == timedelta(0)
    assert decoded_id == 7


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "not-base64",
        "!!!!",
        base64.urlsafe_b64encode(b"not-json").decode(),
        base64.urlsafe_b64encode(
            json.dumps({"v": 2, "at": "2026-01-15T12:00:00+00:00", "id": 1}).encode()
        ).decode(),
        base64.urlsafe_b64encode(
            json.dumps({"v": 1, "at": "2026-01-15T12:00:00", "id": 1}).encode()
        ).decode(),
        base64.urlsafe_b64encode(
            json.dumps({"v": 1, "at": "2026-01-15T12:00:00+00:00", "id": 0}).encode()
        ).decode(),
        base64.urlsafe_b64encode(
            json.dumps({"v": 1, "at": "2026-01-15T12:00:00+00:00", "id": True}).encode()
        ).decode(),
        "a" * 513,
    ],
)
def test_invalid_cursors_are_rejected(cursor: str) -> None:
    with pytest.raises(ValueError):
        decode_cursor(cursor)


def test_cursor_preserves_microseconds() -> None:
    timestamp = datetime(2026, 1, 15, 12, 0, 0, 123456, tzinfo=UTC)
    sample = stored_sample(1, timestamp)

    decoded_time, _ = decode_cursor(encode_cursor(sample))

    assert decoded_time == timestamp
    assert decoded_time.microsecond == 123456
