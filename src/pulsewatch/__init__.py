"""PulseWatch: a Linux-first system monitoring API."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pulsewatch")
except PackageNotFoundError:  # pragma: no cover - only hit from an unpackaged checkout
    __version__ = "0.2.0"

__all__ = ["__version__"]
