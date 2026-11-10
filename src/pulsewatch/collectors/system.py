"""psutil-backed Linux host metrics collection."""

from __future__ import annotations

import os
import platform
import socket
from datetime import UTC, datetime
from pathlib import Path

import psutil

from pulsewatch.api.schemas import (
    CPUMetrics,
    DiskMetrics,
    MemoryMetrics,
    NetworkMetrics,
    SystemSnapshot,
)


def _percent(value: float) -> float:
    return round(float(value), 2)


def _load_average() -> tuple[float, float, float] | None:
    try:
        return os.getloadavg()
    except (AttributeError, OSError):  # pragma: no cover - non-Linux fallback
        return None


class SystemMetricsCollector:
    """Collect CPU, memory, disk, and network data for the local host."""

    def __init__(self, disk_path: Path | str = Path("/")) -> None:
        self.disk_path = Path(disk_path)
        # psutil's non-blocking CPU measurement is relative to the previous
        # call. Prime the counters so the first API request is meaningful.
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)

    def collect(self) -> SystemSnapshot:
        """Gather a snapshot without blocking for a sampling interval."""
        timestamp = datetime.now(UTC)
        boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=UTC)

        cpu_usage = psutil.cpu_percent(interval=None)
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        load_average = _load_average()
        virtual_memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk_usage = psutil.disk_usage(str(self.disk_path))
        disk_io = psutil.disk_io_counters()
        network = psutil.net_io_counters()

        return SystemSnapshot(
            timestamp=timestamp,
            hostname=socket.gethostname(),
            platform=platform.platform(),
            boot_time=boot_time,
            uptime_seconds=max(0.0, round((timestamp - boot_time).total_seconds(), 2)),
            cpu=CPUMetrics(
                usage_percent=_percent(cpu_usage),
                logical_cores=psutil.cpu_count(logical=True) or 1,
                physical_cores=psutil.cpu_count(logical=False),
                per_core_percent=[_percent(value) for value in per_core],
                load_average_1m=load_average[0] if load_average else None,
                load_average_5m=load_average[1] if load_average else None,
                load_average_15m=load_average[2] if load_average else None,
            ),
            memory=MemoryMetrics(
                total_bytes=virtual_memory.total,
                available_bytes=virtual_memory.available,
                used_bytes=virtual_memory.used,
                usage_percent=_percent(virtual_memory.percent),
                swap_total_bytes=swap.total,
                swap_used_bytes=swap.used,
                swap_usage_percent=_percent(swap.percent),
            ),
            disk=DiskMetrics(
                path=str(self.disk_path),
                total_bytes=disk_usage.total,
                used_bytes=disk_usage.used,
                free_bytes=disk_usage.free,
                usage_percent=_percent(disk_usage.percent),
                read_bytes=disk_io.read_bytes if disk_io else 0,
                write_bytes=disk_io.write_bytes if disk_io else 0,
                read_count=disk_io.read_count if disk_io else 0,
                write_count=disk_io.write_count if disk_io else 0,
            ),
            network=NetworkMetrics(
                bytes_sent=network.bytes_sent if network else 0,
                bytes_received=network.bytes_recv if network else 0,
                packets_sent=network.packets_sent if network else 0,
                packets_received=network.packets_recv if network else 0,
                errors_in=network.errin if network else 0,
                errors_out=network.errout if network else 0,
                drops_in=network.dropin if network else 0,
                drops_out=network.dropout if network else 0,
            ),
        )
