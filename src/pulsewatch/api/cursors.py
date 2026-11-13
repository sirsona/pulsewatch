"""Opaque cursor encoding for metric history pagination."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pulsewatch.db.repository import StoredSample

_CURSOR_VERSION = 2
MAX_CURSOR_LENGTH = 512
MAX_HISTORY_WINDOW = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class HistoryWindow:
    """The inclusive UTC window a history cursor belongs to."""

    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class CursorState:
    """The keyset position and window encoded in a history cursor."""

    collected_at: datetime
    sample_id: int
    window: HistoryWindow


def _parse_aware_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        msg = f"cursor {field} is invalid"
        raise ValueError(msg)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        msg = f"cursor {field} is invalid"
        raise ValueError(msg) from exc
    if parsed.tzinfo is None:
        msg = f"cursor {field} must include a timezone"
        raise ValueError(msg)
    return parsed.astimezone(UTC)


def encode_cursor(sample: StoredSample, window: HistoryWindow) -> str:
    """Encode a page position and its window into an opaque cursor."""
    payload = {
        "v": _CURSOR_VERSION,
        "at": sample.snapshot.timestamp.isoformat(),
        "id": sample.id,
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str) -> CursorState:
    """Decode a cursor into its keyset position and bound window.

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

    sample_id = payload.get("id")
    if not isinstance(sample_id, int) or isinstance(sample_id, bool) or sample_id < 1:
        msg = "cursor identity is invalid"
        raise ValueError(msg)

    collected_at = _parse_aware_datetime(payload.get("at"), "timestamp")
    window = HistoryWindow(
        start=_parse_aware_datetime(payload.get("start"), "start"),
        end=_parse_aware_datetime(payload.get("end"), "end"),
    )
    if window.start >= window.end:
        msg = "cursor window is invalid"
        raise ValueError(msg)
    if window.end - window.start > MAX_HISTORY_WINDOW:
        msg = "cursor window exceeds seven days"
        raise ValueError(msg)

    return CursorState(
        collected_at=collected_at,
        sample_id=sample_id,
        window=window,
    )
