"""Kubernetes-style liveness and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from pulsewatch import __version__
from pulsewatch.api.schemas import HealthResponse
from pulsewatch.core.config import Settings
from pulsewatch.core.logging import logger
from pulsewatch.db.errors import StorageUnavailableError
from pulsewatch.db.repository import MetricRepository
from pulsewatch.services.sampler import SamplerService

router = APIRouter(tags=["Health"])


@router.get(
    "/health/live",
    response_model=HealthResponse,
    response_model_exclude_none=True,
    summary="Check that the process is running",
)
def liveness() -> HealthResponse:
    """Return success whenever the application process can serve requests."""
    return HealthResponse(status="ok", service="pulsewatch", version=__version__)


@router.get(
    "/health/ready",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Service is not ready."}},
    summary="Check whether the service is ready to receive traffic",
)
async def readiness(request: Request, response: Response) -> HealthResponse:
    """Check PostgreSQL connectivity and sampler freshness.

    A degraded readiness result intentionally uses the health schema rather than
    the problem-details schema so orchestrators can inspect each dependency.
    """
    settings: Settings = request.app.state.settings
    repository: MetricRepository = request.app.state.repository
    sampler: SamplerService = request.app.state.sampler

    database_ok = True
    try:
        await repository.check_connection()
    except StorageUnavailableError:
        database_ok = False
        logger.warning(
            "readiness database check failed",
            extra={"event": "readiness_database_failed"},
        )

    if settings.sampler_enabled:
        sampler_ok = sampler.is_healthy()
        sampler_status = "ok" if sampler_ok else "stale"
    else:
        sampler_ok = True
        sampler_status = "disabled"

    ready = database_ok and sampler_ok
    if not ready:
        response.status_code = 503

    return HealthResponse(
        status="ok" if ready else "degraded",
        service="pulsewatch",
        version=__version__,
        checks={
            "database": "ok" if database_ok else "unavailable",
            "sampler": sampler_status,
        },
    )
