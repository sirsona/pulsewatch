# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- PostgreSQL-backed metric sample storage using async SQLAlchemy and asyncpg.
- Alembic migration for the `metric_samples` table and its query indexes.
- Background sampler that collects on a configurable interval and persists each
  snapshot.
- PostgreSQL and sampler-freshness checks on `/health/ready`.
- PostgreSQL integration tests and a full Compose-stack CI smoke test.

### Changed

- `/api/v1/metrics/current` now returns the latest persisted sample instead of
  collecting metrics on request.
- Readiness no longer calls psutil and returns `503` with dependency checks when
  degraded.
- Compose now starts PostgreSQL and applies migrations before the API.
- The systemd unit applies migrations before starting the service.

### Planned

- Historical metric query endpoint with time-range filtering.
- Retention policy and cleanup job.
- Production backup/restore automation and load testing.

## [0.1.0] - 2026-11-10

### Added

- FastAPI application with a versioned `/api/v1` namespace.
- psutil collectors for CPU, memory, disk, and network metrics.
- Liveness and readiness probes.
- Structured JSON logging with request correlation IDs.
- RFC 9457 problem-details error contract.
- Typed, environment-driven configuration with `.env` support.
- pytest suite covering configuration, collectors, logging, API, and CLI,
  enforced at 85% branch coverage.
- Ruff and mypy quality gates plus GitHub Actions CI.
- Container image build and health-check smoke test in CI.
- Hatchling packaging with a `pulsewatch` console entrypoint.
- Multi-stage, non-root Docker image and Compose deployment.
- Hardened systemd unit and deployment documentation.
- README, API contract, architecture notes, contributing, and security policies.

[Unreleased]: https://github.com/sirsona/pulsewatch/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sirsona/pulsewatch/releases/tag/v0.1.0
