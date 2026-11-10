"""Command-line entrypoint for local and systemd execution."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

import uvicorn

from pulsewatch import __version__
from pulsewatch.core.config import get_settings
from pulsewatch.core.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="pulsewatch",
        description="Run the PulseWatch system monitoring API.",
    )
    parser.add_argument("--host", help="Bind address (default: PULSEWATCH_HOST)")
    parser.add_argument("--port", type=int, help="Bind port (default: PULSEWATCH_PORT)")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging threshold (default: PULSEWATCH_LOG_LEVEL)",
    )
    parser.add_argument(
        "--environment",
        choices=["development", "test", "production"],
        help="Deployment environment (default: PULSEWATCH_ENVIRONMENT)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Restart on source changes. Intended for local development only.",
    )
    parser.add_argument("--version", action="version", version=f"pulsewatch {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Parse arguments, configure logging, and start the ASGI server."""
    args = build_parser().parse_args(argv)

    overrides = {
        "PULSEWATCH_HOST": args.host,
        "PULSEWATCH_PORT": str(args.port) if args.port is not None else None,
        "PULSEWATCH_LOG_LEVEL": args.log_level,
        "PULSEWATCH_ENVIRONMENT": args.environment,
    }
    for variable, value in overrides.items():
        if value is not None:
            os.environ[variable] = str(value)

    get_settings.cache_clear()
    settings = get_settings()
    configure_logging(settings)

    uvicorn.run(
        "pulsewatch.main:app",
        host=settings.host,
        port=settings.port,
        reload=args.reload,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
