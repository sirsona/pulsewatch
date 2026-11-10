"""Tests for psutil-backed metric collection."""

from __future__ import annotations

import os
import platform
import socket
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest

from pulsewatch.collectors.system import SystemMetricsCollector


def fake_virtual_memory() -> SimpleNamespace:
    return SimpleNamespace(
        total=16_000,
        available=10_000,
        used=6_000,
        percent=37.5,
    )


def fake_swap_memory() -> SimpleNamespace:
    return SimpleNamespace(total=4_000, used=1_000, percent=25.0)


def fake_disk_usage(path: str) -> SimpleNamespace:
    assert path == "/data"
    return SimpleNamespace(total=100_000, used=40_000, free=60_000, percent=40.0)


def fake_disk_io() -> SimpleNamespace:
    return SimpleNamespace(
        read_bytes=1_000,
        write_bytes=2_000,
        read_count=10,
        write_count=20,
    )


def fake_network_io() -> SimpleNamespace:
    return SimpleNamespace(
        bytes_sent=100,
        bytes_recv=200,
        packets_sent=30,
        packets_recv=40,
        errin=1,
        errout=2,
        dropin=3,
        dropout=4,
    )


def fake_cpu_percent(*, interval: float | None = None, percpu: bool = False) -> float | list[float]:
    assert interval is None
    if percpu:
        return [10.0, 20.0]
    return 15.0


def fake_cpu_count(*, logical: bool = True) -> int:
    return 2 if logical else 1


@pytest.fixture
def patched_psutil(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(psutil, "cpu_percent", fake_cpu_percent)
    monkeypatch.setattr(psutil, "cpu_count", fake_cpu_count)
    monkeypatch.setattr(psutil, "boot_time", lambda: 1_700_000_000.0)
    monkeypatch.setattr(psutil, "virtual_memory", fake_virtual_memory)
    monkeypatch.setattr(psutil, "swap_memory", fake_swap_memory)
    monkeypatch.setattr(psutil, "disk_usage", fake_disk_usage)
    monkeypatch.setattr(psutil, "disk_io_counters", fake_disk_io)
    monkeypatch.setattr(psutil, "net_io_counters", fake_network_io)
    monkeypatch.setattr(os, "getloadavg", lambda: (0.5, 1.0, 1.5))
    monkeypatch.setattr(socket, "gethostname", lambda: "collector-host")
    monkeypatch.setattr(platform, "platform", lambda: "Linux-test")


def test_collect_returns_all_metric_families(patched_psutil: None) -> None:
    collector = SystemMetricsCollector(disk_path="/data")

    snapshot = collector.collect()

    assert snapshot.hostname == "collector-host"
    assert snapshot.platform == "Linux-test"
    assert snapshot.cpu.usage_percent == 15.0
    assert snapshot.cpu.logical_cores == 2
    assert snapshot.cpu.physical_cores == 1
    assert snapshot.cpu.per_core_percent == [10.0, 20.0]
    assert snapshot.cpu.load_average_1m == 0.5
    assert snapshot.cpu.load_average_5m == 1.0
    assert snapshot.cpu.load_average_15m == 1.5
    assert snapshot.memory.total_bytes == 16_000
    assert snapshot.memory.usage_percent == 37.5
    assert snapshot.memory.swap_used_bytes == 1_000
    assert snapshot.disk.path == "/data"
    assert snapshot.disk.usage_percent == 40.0
    assert snapshot.disk.write_bytes == 2_000
    assert snapshot.network.bytes_received == 200
    assert snapshot.network.drops_out == 4
    assert snapshot.uptime_seconds > 0


def test_missing_load_average_is_null(
    patched_psutil: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unsupported() -> tuple[float, float, float]:
        msg = "load average unavailable"
        raise OSError(msg)

    monkeypatch.setattr(os, "getloadavg", unsupported)

    snapshot = SystemMetricsCollector(disk_path="/data").collect()

    assert snapshot.cpu.load_average_1m is None
    assert snapshot.cpu.load_average_5m is None
    assert snapshot.cpu.load_average_15m is None


def test_missing_io_counters_default_to_zero(
    patched_psutil: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(psutil, "disk_io_counters", lambda: None)
    monkeypatch.setattr(psutil, "net_io_counters", lambda: None)
    collector = SystemMetricsCollector(disk_path="/data")

    snapshot = collector.collect()

    assert snapshot.disk.read_bytes == 0
    assert snapshot.disk.write_count == 0
    assert snapshot.network.bytes_received == 0
    assert snapshot.network.drops_in == 0


def test_default_disk_path_is_root(patched_psutil: None) -> None:
    collector = SystemMetricsCollector()

    assert collector.disk_path == Path("/")
