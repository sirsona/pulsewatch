"""Host metric endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from pulsewatch.api.cursors import (
    MAX_CURSOR_LENGTH,
    MAX_HISTORY_WINDOW,
    CursorState,
    HistoryWindow,
    decode_cursor,
    encode_cursor,
)
from pulsewatch.api.schemas import HistoryResponse, SystemSnapshot
from pulsewatch.core.logging import logger
from pulsewatch.db.errors import StorageUnavailableError
from pulsewatch.db.repository import MetricRepository

router = APIRouter(prefix="/metrics", tags=["Metrics"])

_DEFAULT_HISTORY_WINDOW = timedelta(hours=1)
_MAX_HISTORY_LIMIT = 1000


def _normalise_history_window(
    start: datetime | None,
    end: datetime | None,
    *,
    cursor_window: HistoryWindow | None = None,
) -> tuple[datetime, datetime]:
    """Apply defaults and validate the requested UTC history window."""
    if cursor_window is not None and start is None and end is None:
        return cursor_window.start, cursor_window.end

    now = datetime.now(UTC)
    end_time = end or now
    start_time = start or (end_time - _DEFAULT_HISTORY_WINDOW)

    if start_time.tzinfo is None or end_time.tzinfo is None:
        raise HTTPException(
            status_code=422,
            detail="start and end must include a timezone.",
        )

    start_utc = start_time.astimezone(UTC)
    end_utc = end_time.astimezone(UTC)
    if start_utc >= end_utc:
        raise HTTPException(
            status_code=422,
            detail="start must be earlier than end.",
        )
    if end_utc - start_utc > MAX_HISTORY_WINDOW:
        raise HTTPException(
            status_code=422,
            detail="The history window cannot exceed 7 days.",
        )
    if cursor_window is not None and (
        start_utc != cursor_window.start or end_utc != cursor_window.end
    ):
        raise HTTPException(
            status_code=422,
            detail="The cursor belongs to a different history window.",
        )
    return start_utc, end_utc


@router.get(
    "/history",
    response_model=HistoryResponse,
    summary="Get a page of persisted host metrics",
    responses={
        422: {
            "description": "The time window or cursor is invalid.",
            "content": {"application/problem+json": {}},
        },
        503: {
            "description": "The metrics store is unavailable.",
            "content": {"application/problem+json": {}},
        },
    },
)
async def history_metrics(
    request: Request,
    start: Annotated[
        datetime | None,
        Query(description="Inclusive UTC start. Defaults to one hour before end."),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(description="Inclusive UTC end. Defaults to now."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_HISTORY_LIMIT)] = 100,
    cursor: Annotated[
        str | None,
        Query(
            max_length=MAX_CURSOR_LENGTH,
            description="Opaque next_cursor value from a previous page.",
        ),
    ] = None,
) -> HistoryResponse:
    """Return newest-first samples within an inclusive, bounded time range."""
    cursor_state: CursorState | None = None
    if cursor is not None:
        try:
            cursor_state = decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    start_utc, end_utc = _normalise_history_window(
        start,
        end,
        cursor_window=cursor_state.window if cursor_state is not None else None,
    )
    before = (
        (cursor_state.collected_at, cursor_state.sample_id) if cursor_state is not None else None
    )

    repository: MetricRepository = request.app.state.repository
    try:
        records = await repository.list_snapshots(
            start=start_utc,
            end=end_utc,
            limit=limit + 1,
            before=before,
        )
    except StorageUnavailableError as exc:
        logger.exception(
            "failed to read metric history",
            extra={"event": "history_read_failed"},
        )
        raise HTTPException(
            status_code=503,
            detail="The metrics store is unavailable.",
        ) from exc

    has_more = len(records) > limit
    page = records[:limit]
    next_cursor = (
        encode_cursor(page[-1], HistoryWindow(start=start_utc, end=end_utc))
        if has_more and page
        else None
    )

    return HistoryResponse(
        start=start_utc,
        end=end_utc,
        limit=limit,
        count=len(page),
        next_cursor=next_cursor,
        samples=[record.snapshot for record in page],
    )


@router.get(
    "/current",
    response_model=SystemSnapshot,
    summary="Get the latest stored host metrics snapshot",
    responses={
        503: {
            "description": "No sample is available yet or the metrics store is unavailable.",
            "content": {"application/problem+json": {}},
        }
    },
)
async def current_metrics(request: Request) -> SystemSnapshot:
    """Return the most recent sample written by the background sampler.

    psutil collection happens only in the sampler, which gives CPU usage a
    stable measurement window and keeps requests fast.
    """
    repository: MetricRepository = request.app.state.repository
    try:
        snapshot = await repository.latest_snapshot()
    except StorageUnavailableError as exc:
        logger.exception(
            "failed to read the latest metric sample",
            extra={"event": "metrics_read_failed"},
        )
        raise HTTPException(
            status_code=503,
            detail="The metrics store is unavailable.",
        ) from exc

    if snapshot is None:
        raise HTTPException(
            status_code=503,
            detail="No metrics samples are available yet.",
        )
    return snapshot
