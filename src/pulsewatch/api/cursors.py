"""Opaque cursor encoding for metric history pagination."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime

from pulsewatch.db.repository import StoredSample

_CURSOR_VERSION = 1
MAX_CURSOR_LENGTH = 512


def encode_cursor(sample: StoredSample) -> str:
    """Encode the last sample on a page into an opaque cursor."""
    payload = {
        "v": _CURSOR_VERSION,
        "at": sample.snapshot.timestamp.isoformat(),
        "id": sample.id,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    """Decode a cursor into a collection timestamp and row identity.

    Raises:
        ValueError: if the cursor is malformed, unsupported, or not timezone-aware.
    """
    if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
        msg = "cursor is empty or too long"
        raise ValueError(msg)

    padding = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + padding)
        payload = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        msg = "cursor is not valid base64 JSON"
        raise ValueError(msg) from exc

    if not isinstance(payload, dict) or payload.get("v") != _CURSOR_VERSION:
        msg = "unsupported cursor version"
        raise ValueError(msg)

    timestamp_value = payload.get("at")
    sample_id = payload.get("id")
    if (
        not isinstance(timestamp_value, str)
        or not isinstance(sample_id, int)
        or isinstance(sample_id, bool)
        or sample_id < 1
    ):
        msg = "cursor fields are invalid"
        raise ValueError(msg)

    try:
        timestamp = datetime.fromisoformat(timestamp_value)
    except ValueError as exc:
        msg = "cursor timestamp is invalid"
        raise ValueError(msg) from exc
    if timestamp.tzinfo is None:
        msg = "cursor timestamp must include a timezone"
        raise ValueError(msg)

    return timestamp.astimezone(UTC), sample_id
