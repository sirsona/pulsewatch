"""Host metric endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from pulsewatch.api.schemas import SystemSnapshot
from pulsewatch.core.logging import logger
from pulsewatch.db.repository import MetricRepository

router = APIRouter(prefix="/metrics", tags=["Metrics"])


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
    except Exception as exc:
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
