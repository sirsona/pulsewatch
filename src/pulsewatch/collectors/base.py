"""Collector interface used by the API and, later, the sampling worker."""

from __future__ import annotations

from typing import Protocol

from pulsewatch.api.schemas import SystemSnapshot


class MetricsCollector(Protocol):
    """A synchronous source of host telemetry."""

    def collect(self) -> SystemSnapshot:
        """Return a consistent snapshot of the host's current metrics."""
        ...
