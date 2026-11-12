"""Periodic, batched retention cleanup for stored metric samples."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta

from pulsewatch.core.logging import logger
from pulsewatch.db.repository import MetricRepository


class RetentionService:
    """Delete samples older than the configured retention window."""

    def __init__(
        self,
        repository: MetricRepository,
        *,
        retention_days: int,
        interval_seconds: float,
        batch_size: int,
    ) -> None:
        self._repository = repository
        self._retention_days = retention_days
        self._interval_seconds = interval_seconds
        self._batch_size = batch_size
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        """Whether the background cleanup task is active."""
        return self._task is not None and not self._task.done()

    async def cleanup_once(self, *, now: datetime | None = None) -> int:
        """Delete all expired samples in bounded batches."""
        cutoff = (now or datetime.now(UTC)) - timedelta(days=self._retention_days)
        total = 0
        while True:
            deleted = await self._repository.delete_samples_before(
                cutoff,
                batch_size=self._batch_size,
            )
            total += deleted
            if deleted < self._batch_size:
                break

        if total:
            logger.info(
                "retention cleanup completed",
                extra={"event": "retention_cleanup", "deleted_count": total},
            )
        return total

    async def run(self) -> None:
        """Run cleanup until stopped, logging failures without exiting."""
        logger.info("retention service started", extra={"event": "retention_started"})
        try:
            while not self._stop_event.is_set():
                started = time.monotonic()
                try:
                    await self.cleanup_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "retention cleanup failed",
                        extra={"event": "retention_failed"},
                    )

                elapsed = time.monotonic() - started
                delay = max(0.0, self._interval_seconds - elapsed)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                except TimeoutError:
                    continue
        finally:
            logger.info("retention service stopped", extra={"event": "retention_stopped"})

    def start(self) -> None:
        """Start the retention task if it is not already running."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self.run(), name="pulsewatch-retention")

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
            logger.exception("retention service stopped unexpectedly")
        finally:
            self._task = None
