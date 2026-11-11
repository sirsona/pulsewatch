"""Background metric sampling loop."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from pulsewatch.api.schemas import SystemSnapshot
from pulsewatch.collectors.base import MetricsCollector
from pulsewatch.core.logging import logger
from pulsewatch.db.repository import MetricRepository


class SamplerService:
    """Collect and persist snapshots on a fixed cadence."""

    def __init__(
        self,
        collector: MetricsCollector,
        repository: MetricRepository,
        *,
        interval_seconds: float,
        stale_after_seconds: float,
    ) -> None:
        self._collector = collector
        self._repository = repository
        self._interval_seconds = interval_seconds
        self._stale_after_seconds = stale_after_seconds
        self._last_success_at: datetime | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def last_success_at(self) -> datetime | None:
        """When the sampler last wrote a sample successfully."""
        return self._last_success_at

    @property
    def is_running(self) -> bool:
        """Whether the background task is active."""
        return self._task is not None and not self._task.done()

    def is_healthy(self, *, now: datetime | None = None) -> bool:
        """Return whether the latest sample is within the freshness window."""
        if self._last_success_at is None:
            return False
        current = now or datetime.now(UTC)
        age = (current - self._last_success_at).total_seconds()
        return age <= self._stale_after_seconds

    async def sample_once(self) -> SystemSnapshot:
        """Collect and persist one snapshot, updating sampler freshness."""
        snapshot = await asyncio.to_thread(self._collector.collect)
        await self._repository.save_snapshot(snapshot)
        self._last_success_at = datetime.now(UTC)
        return snapshot

    async def run(self) -> None:
        """Run until stopped, logging failures without killing the loop."""
        logger.info("sampler started", extra={"event": "sampler_started"})
        try:
            while not self._stop_event.is_set():
                started = time.monotonic()
                try:
                    await self.sample_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "metric sampling failed",
                        extra={"event": "sampling_failed"},
                    )

                elapsed = time.monotonic() - started
                delay = max(0.0, self._interval_seconds - elapsed)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                except TimeoutError:
                    continue
        finally:
            logger.info("sampler stopped", extra={"event": "sampler_stopped"})

    def start(self) -> None:
        """Start the background task if it is not already running."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self.run(), name="pulsewatch-sampler")

    async def stop(self) -> None:
        """Signal the loop to stop and wait for it to finish."""
        task = self._task
        if task is None:
            return
        self._stop_event.set()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:  # pragma: no cover - defensive shutdown boundary
            logger.exception("sampler stopped unexpectedly")
        finally:
            self._task = None
