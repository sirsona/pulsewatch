"""Pydantic contracts for API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Liveness or readiness state for the service."""

    status: Literal["ok", "degraded"]
    service: str
    version: str
    checks: dict[str, str] | None = None


class ServiceInfo(BaseModel):
    """Discoverability metadata for the running service."""

    name: str
    version: str
    environment: str
    documentation: str | None
    health: dict[str, str]


class CPUMetrics(BaseModel):
    """CPU utilisation and load averages."""

    model_config = ConfigDict(frozen=True)

    usage_percent: float = Field(ge=0, le=100)
    logical_cores: int = Field(ge=1)
    physical_cores: int | None = Field(default=None, ge=1)
    per_core_percent: list[float]
    load_average_1m: float | None = None
    load_average_5m: float | None = None
    load_average_15m: float | None = None


class MemoryMetrics(BaseModel):
    """Physical and swap memory usage in bytes."""

    model_config = ConfigDict(frozen=True)

    total_bytes: int = Field(ge=0)
    available_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    usage_percent: float = Field(ge=0, le=100)
    swap_total_bytes: int = Field(ge=0)
    swap_used_bytes: int = Field(ge=0)
    swap_usage_percent: float = Field(ge=0, le=100)


class DiskMetrics(BaseModel):
    """Capacity and cumulative I/O for the configured filesystem."""

    model_config = ConfigDict(frozen=True)

    path: str
    total_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    free_bytes: int = Field(ge=0)
    usage_percent: float = Field(ge=0, le=100)
    read_bytes: int = Field(default=0, ge=0)
    write_bytes: int = Field(default=0, ge=0)
    read_count: int = Field(default=0, ge=0)
    write_count: int = Field(default=0, ge=0)


class NetworkMetrics(BaseModel):
    """Cumulative host-wide network counters since boot."""

    model_config = ConfigDict(frozen=True)

    bytes_sent: int = Field(ge=0)
    bytes_received: int = Field(ge=0)
    packets_sent: int = Field(ge=0)
    packets_received: int = Field(ge=0)
    errors_in: int = Field(default=0, ge=0)
    errors_out: int = Field(default=0, ge=0)
    drops_in: int = Field(default=0, ge=0)
    drops_out: int = Field(default=0, ge=0)


class SystemSnapshot(BaseModel):
    """One point-in-time view of host telemetry."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    hostname: str
    platform: str
    boot_time: datetime
    uptime_seconds: float = Field(ge=0)
    cpu: CPUMetrics
    memory: MemoryMetrics
    disk: DiskMetrics
    network: NetworkMetrics


class HistoryResponse(BaseModel):
    """A bounded, descending page of persisted metric snapshots."""

    start: datetime
    end: datetime
    limit: int
    count: int
    next_cursor: str | None
    samples: list[SystemSnapshot]
