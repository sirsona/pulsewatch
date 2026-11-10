# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- PostgreSQL persistence and metric history endpoints.
- Background sampler, retention policy, and Alembic migrations.
- Integration tests against PostgreSQL.

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
- Hatchling packaging with a `pulsewatch` console entrypoint.
- Multi-stage, non-root Docker image and Compose deployment.
- Hardened systemd unit and deployment documentation.
- README, API contract, architecture notes, contributing, and security policies.

[Unreleased]: https://github.com/sirsona/pulsewatch/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sirsona/pulsewatch/releases/tag/v0.1.0
