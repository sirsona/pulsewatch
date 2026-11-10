"""Kubernetes-style liveness and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from pulsewatch import __version__
from pulsewatch.api.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health/live",
    response_model=HealthResponse,
    summary="Check that the process is running",
)
def liveness() -> HealthResponse:
    """Return success whenever the application process can serve requests."""
    return HealthResponse(status="ok", service="pulsewatch", version=__version__)


@router.get(
    "/health/ready",
    response_model=HealthResponse,
    summary="Check whether the service is ready to receive traffic",
)
def readiness(request: Request) -> HealthResponse:
    """Report readiness of dependencies used to serve API traffic.

    Persistence and sampling dependencies will be added to this check as those
    components land. Today the API has no required external dependencies.
    """
    request.app.state.collector.collect()
    return HealthResponse(
        status="ok",
        service="pulsewatch",
        version=__version__,
        checks={"api": "ok", "collector": "ok"},
    )
