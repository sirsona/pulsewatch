"""FastAPI application factory and entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pulsewatch import __version__
from pulsewatch.api import health, metrics
from pulsewatch.api.schemas import ServiceInfo
from pulsewatch.collectors.base import MetricsCollector
from pulsewatch.collectors.system import SystemMetricsCollector
from pulsewatch.core.config import Settings, get_settings
from pulsewatch.core.errors import register_exception_handlers
from pulsewatch.core.logging import configure_logging, logger
from pulsewatch.core.middleware import RequestContextMiddleware

API_PREFIX = "/api/v1"

TAGS_METADATA = [
    {"name": "Service", "description": "Service metadata and discovery."},
    {"name": "Health", "description": "Probes for process liveness and readiness."},
    {"name": "Metrics", "description": "Point-in-time host telemetry."},
]


def create_app(
    settings: Settings | None = None,
    collector: MetricsCollector | None = None,
) -> FastAPI:
    """Build an application instance.

    Dependency injection at the factory boundary keeps the app testable without
    patching global state, and allows future adapters for persistence.
    """
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings)
    metrics_collector = collector or SystemMetricsCollector(disk_path=resolved_settings.disk_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "PulseWatch service started",
            extra={"event": "startup"},
        )
        yield
        logger.info(
            "PulseWatch service stopped",
            extra={"event": "shutdown"},
        )

    docs_url = "/docs" if resolved_settings.docs_enabled else None
    openapi_url = "/openapi.json" if resolved_settings.docs_enabled else None

    app = FastAPI(
        title="PulseWatch API",
        summary="Linux-first host metrics over a versioned REST API.",
        description=(
            "PulseWatch exposes CPU, memory, disk, and network telemetry for the "
            "host it runs on. All errors are returned as RFC 9457 problem details."
        ),
        version=__version__,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
    )

    app.state.settings = resolved_settings
    app.state.collector = metrics_collector

    app.add_middleware(
        RequestContextMiddleware,
        header_name=resolved_settings.request_id_header,
    )
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(metrics.router, prefix=API_PREFIX)

    @app.get(
        "/",
        response_model=ServiceInfo,
        tags=["Service"],
        summary="Discover service metadata",
    )
    def service_info() -> ServiceInfo:
        return ServiceInfo(
            name="pulsewatch",
            version=__version__,
            environment=resolved_settings.environment,
            documentation=docs_url,
            health={"live": "/health/live", "ready": "/health/ready"},
        )

    return app


app = create_app()
