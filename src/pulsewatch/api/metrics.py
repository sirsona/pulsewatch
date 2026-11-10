"""Host metric endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from pulsewatch.api.schemas import SystemSnapshot
from pulsewatch.collectors.base import MetricsCollector

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get(
    "/current",
    response_model=SystemSnapshot,
    summary="Get a current host metrics snapshot",
    responses={
        500: {
            "description": "The host metrics could not be collected.",
            "content": {"application/problem+json": {}},
        }
    },
)
def current_metrics(request: Request) -> SystemSnapshot:
    """Collect CPU, memory, disk, and network metrics synchronously.

    FastAPI runs this synchronous route in a worker thread, keeping blocking
    psutil calls off the event loop.
    """
    collector: MetricsCollector = request.app.state.collector
    return collector.collect()
