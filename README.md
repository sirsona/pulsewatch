<div align="center">
  <img src="docs/assets/banner.svg" alt="PulseWatch — Linux-first system telemetry, delivered as an API" width="100%">
</div>

<h1 align="center">PulseWatch</h1>

<p align="center">
  A Linux-first system monitoring service built with Python, FastAPI, psutil, and PostgreSQL.
  <br>
  Sampled. Stored. Observable. Tested.
</p>

<p align="center">
  <a href="https://github.com/sirsona/pulsewatch/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/sirsona/pulsewatch/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/sirsona/pulsewatch/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-22d3ee"></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-3776ab?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-17-4169e1?logo=postgresql&logoColor=white">
</p>

> [!NOTE]
> **Project status: `v0.2.1`.** PulseWatch samples host metrics on a fixed
> cadence, stores them in PostgreSQL, serves the latest sample and bounded
> history, and removes expired data. See the [roadmap](#roadmap).

## Overview

PulseWatch runs a single background sampler against the local Linux host,
persists each snapshot in PostgreSQL, exposes the latest sample and bounded
history over a versioned HTTP API, and deletes expired samples on a retention
schedule. It is designed to run as a hardened **systemd** service or as a
**Docker Compose** stack.

The service is intentionally built beyond the happy path:

- typed, validated configuration
- one psutil collection path with a fixed sampling interval
- PostgreSQL storage through an async repository
- Alembic-managed schema
- cursor-paginated history queries
- batched retention cleanup
- RFC 9457 error responses and request correlation IDs
- structured JSON logs
- unit and PostgreSQL integration tests
- reproducible packaging, CI, and deployment assets

### What works today

| Capability | Status |
| --- | --- |
| CPU, memory, disk, and network sampling | ✅ Implemented |
| PostgreSQL-backed sample storage | ✅ Implemented |
| Alembic migration | ✅ Implemented |
| Background sampler with configurable interval | ✅ Implemented |
| Latest stored metrics endpoint | ✅ Implemented |
| Database- and sampler-aware readiness | ✅ Implemented |
| Structured JSON logs + request IDs | ✅ Implemented |
| RFC 9457 problem-details errors | ✅ Implemented |
| Typed config, Ruff, mypy, pytest, coverage gate | ✅ Implemented |
| PostgreSQL integration tests + full-stack CI | ✅ Implemented |
| Multi-stage Docker image + Compose stack | ✅ Implemented |
| Hardened systemd unit + static verification | ✅ Included; live install untested |
| Historical metrics endpoint | ✅ Implemented |
| Batched retention cleanup | ✅ Implemented |

## Architecture

```mermaid
flowchart LR
    client[Operator / probe] -->|JSON over HTTP| api

    subgraph process["PulseWatch process"]
        direction TB
        api[FastAPI app]
        middleware[Request ID + access logs]
        sampler[Background sampler]
        retention[Retention service]
        collector[psutil collector]
        repository[Async repository]
        api --> middleware
        sampler --> collector
        sampler --> repository
        retention --> repository
        api --> repository
    end

    collector -->|/proc, /sys| kernel[(Linux kernel)]
    repository -->|SQLAlchemy + asyncpg| postgres[(PostgreSQL)]
    probes[systemd / Docker healthcheck] --> health[Health probes]
    health --> api
```

The sampler is the only component that collects metrics. It runs immediately at
startup and then on the configured interval, writing each snapshot through the
repository. The collector primes its CPU counters once during construction. The
current and history endpoints read stored samples rather than triggering another
collection. Retention deletes expired samples in bounded batches.

Readiness checks PostgreSQL connectivity and sampler freshness. Liveness remains
a cheap process-level check.

See [docs/architecture.md](docs/architecture.md) for the request and sampling
lifecycle.

## Quick start

### Docker Compose — recommended

Requirements: Docker with Compose v2.

```bash
git clone https://github.com/sirsona/pulsewatch.git
cd pulsewatch
docker compose up --build --detach
```

Compose starts PostgreSQL, waits for it to become healthy, runs the Alembic
migration, then starts the API. The sampler writes its first sample immediately.

```bash
docker compose ps
curl -s http://127.0.0.1:8000/health/ready | python -m json.tool
curl -s http://127.0.0.1:8000/api/v1/metrics/current | python -m json.tool
```

Open:

- **Interactive docs:** <http://127.0.0.1:8000/docs>
- **Readiness:** <http://127.0.0.1:8000/health/ready>
- **Latest metrics:** <http://127.0.0.1:8000/api/v1/metrics/current>

Stop the stack with:

```bash
docker compose down
# Add --volumes to remove the PostgreSQL data volume.
```

### Local Python development

Requirements: Linux, Python **3.12+**, [uv](https://docs.astral.sh/uv/),
PostgreSQL **15+**, and a reachable database.

```bash
uv sync
cp .env.example .env
# Edit PULSEWATCH_DATABASE_URL if your database differs from the default.

make run
```

`make run` applies migrations before starting the reload server. If you start the
CLI directly, run `uv run pulsewatch-migrate` first.

The default configuration expects:

```text
postgresql+asyncpg://pulsewatch:pulsewatch@127.0.0.1:5432/pulsewatch
```

### Run the quality gates

```bash
make check            # formatting, lint, types, tests, systemd verification
make test             # pytest only
make test-integration # PostgreSQL tests; requires PULSEWATCH_TEST_DATABASE_URL
make lint             # Ruff
make typecheck        # mypy
make verify-unit      # static systemd unit verification
make migrate          # apply migrations with pulsewatch-migrate
```

The suite enforces **85% branch coverage**. CI runs on Python 3.12 and 3.13,
runs the PostgreSQL integration tests, statically verifies the systemd unit,
builds the image, and boots the complete Compose stack before checking readiness,
current metrics, and history.

To run the PostgreSQL integration test locally, apply migrations and provide a
test database URL:

```bash
export PULSEWATCH_DATABASE_URL=postgresql+asyncpg://pulsewatch:pulsewatch@127.0.0.1:5432/pulsewatch_test
export PULSEWATCH_TEST_DATABASE_URL=$PULSEWATCH_DATABASE_URL

make migrate
make test-integration
```

### Migrations and packaging

`pulsewatch-migrate` is the supported migration entrypoint. It is included in
installed wheels, so migrations work without a repository checkout or an
`alembic.ini` in the current directory:

```bash
uv run pulsewatch-migrate
```

Use `PULSEWATCH_MIGRATION_DATABASE_URL` to run migrations with a DDL role while
the API uses a separate DML role. The source distribution includes the deployment,
documentation, and migration assets; the wheel includes the migration scripts and
the migration CLI.

## API

Application data endpoints are versioned under `/api/v1`; the root discovery
endpoint and operational probes are unversioned.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Service metadata and links |
| `GET` | `/health/live` | Process liveness probe |
| `GET` | `/health/ready` | PostgreSQL and sampler readiness |
| `GET` | `/api/v1/metrics/current` | Latest persisted host metrics snapshot |
| `GET` | `/api/v1/metrics/history` | Bounded, cursor-paginated history |
| `GET` | `/docs` | Interactive OpenAPI documentation |
| `GET` | `/openapi.json` | OpenAPI schema |

`/health/ready` returns `200` when the database is reachable and the latest
sample is fresh. It returns `503` with a degraded health body when either check
fails. It does not call psutil.

`/api/v1/metrics/current` returns `503` until the first sample is stored or when
the metrics store is unavailable.

History accepts `start`, `end`, `limit`, and `cursor`:

```bash
curl -G http://127.0.0.1:8000/api/v1/metrics/history \
  --data-urlencode 'limit=100'
```

The default window is the last hour. Windows are inclusive, limited to seven
days, and ordered newest first. The response includes `next_cursor`; pass it back
as `cursor` for the next page. Omit `start`/`end` on the next request to reuse the
cursor’s bound window, or pass the identical window explicitly. Mismatched
windows and malformed cursors return `422`.

### Sample response

```json
{
  "timestamp": "2026-11-10T17:02:43.521912Z",
  "hostname": "ops-01",
  "platform": "Linux-6.8.0-45-generic-x86_64-with-glibc2.39",
  "boot_time": "2026-11-10T06:58:31+00:00",
  "uptime_seconds": 36252.52,
  "cpu": {
    "usage_percent": 14.2,
    "logical_cores": 8,
    "physical_cores": 4,
    "per_core_percent": [11.0, 18.5, 9.0, 25.0, 12.5, 8.0, 15.0, 14.0],
    "load_average_1m": 0.42,
    "load_average_5m": 0.31,
    "load_average_15m": 0.28
  },
  "memory": {
    "total_bytes": 16777216000,
    "available_bytes": 9437184000,
    "used_bytes": 7340032000,
    "usage_percent": 43.8,
    "swap_total_bytes": 2147483648,
    "swap_used_bytes": 0,
    "swap_usage_percent": 0.0
  },
  "disk": {
    "path": "/",
    "total_bytes": 511101108224,
    "used_bytes": 214748364800,
    "free_bytes": 296352743424,
    "usage_percent": 42.0,
    "read_bytes": 918273645,
    "write_bytes": 1827364550,
    "read_count": 82173,
    "write_count": 194822
  },
  "network": {
    "bytes_sent": 718293645,
    "bytes_received": 1329182736,
    "packets_sent": 918273,
    "packets_received": 1428372,
    "errors_in": 0,
    "errors_out": 0,
    "drops_in": 0,
    "drops_out": 0
  }
}
```

### Error contract

Errors use `application/problem+json` ([RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)):

```json
{
  "type": "about:blank",
  "title": "Service Unavailable",
  "status": 503,
  "detail": "The metrics store is unavailable.",
  "instance": "/api/v1/metrics/current",
  "code": "http_503",
  "request_id": "a3f4f9d6c1e84b7a9f0d2e6b8c4a1f37"
}
```

Every response carries an `X-Request-ID` header. A caller-supplied ID is reused
when it matches a conservative allow-list, otherwise a new ID is generated.

See [docs/api.md](docs/api.md) for the complete contract.

## Data model

The `metric_samples` table stores:

- `id` — identity primary key
- `collected_at` — UTC collection timestamp, indexed
- `hostname` — sampled host
- `cpu_usage_percent`, `memory_usage_percent`, `disk_usage_percent` — scalar
  fields for efficient filtering
- `payload` — full validated snapshot as PostgreSQL `JSONB`

The schema is managed with Alembic under `migrations/`.

## Configuration

Settings are loaded from environment variables prefixed with `PULSEWATCH_`, or
from a local `.env` file. Unknown variables are ignored.

| Variable | Default | Notes |
| --- | --- | --- |
| `PULSEWATCH_ENVIRONMENT` | `development` | `development`, `test`, or `production` |
| `PULSEWATCH_HOST` | `127.0.0.1` | Bind address |
| `PULSEWATCH_PORT` | `8000` | Bind port, 1–65535 |
| `PULSEWATCH_LOG_LEVEL` | `INFO` | `DEBUG` through `CRITICAL` |
| `PULSEWATCH_LOG_FORMAT` | `json` | `json` for services, `console` locally |
| `PULSEWATCH_DISK_PATH` | `/` | Existing filesystem mount to report |
| `PULSEWATCH_REQUEST_ID_HEADER` | `X-Request-ID` | Correlation header name |
| `PULSEWATCH_DOCS_ENABLED` | `true` | Disable `/docs` and `/openapi.json` in production |
| `PULSEWATCH_DATABASE_URL` | local PostgreSQL URL | Must use `postgresql+asyncpg://`; treated as a secret |
| `PULSEWATCH_MIGRATION_DATABASE_URL` | unset | Optional dedicated DDL role for migrations; defaults to `PULSEWATCH_DATABASE_URL` |
| `PULSEWATCH_SAMPLER_ENABLED` | `true` | Set `false` only for API-only tests or maintenance |
| `PULSEWATCH_SAMPLE_INTERVAL_SECONDS` | `15` | Minimum 1 second |
| `PULSEWATCH_SAMPLER_STALE_AFTER_SECONDS` | `45` | Must be at least the sampling interval |
| `PULSEWATCH_RETENTION_ENABLED` | `true` | Enable periodic expired-sample cleanup |
| `PULSEWATCH_RETENTION_DAYS` | `7` | Samples older than this are deleted |
| `PULSEWATCH_RETENTION_CLEANUP_INTERVAL_SECONDS` | `3600` | Cleanup cadence, minimum 60s |
| `PULSEWATCH_RETENTION_BATCH_SIZE` | `1000` | Maximum rows deleted per batch |

`.env` is ignored by Git. Start from [.env.example](.env.example).

## Deployment

### Docker Compose

```bash
docker compose up --build --detach
docker compose ps
docker compose logs -f pulsewatch
```

The Compose stack includes PostgreSQL with a persistent volume, runs
`pulsewatch-migrate` before starting the API, and gives the app a readiness
health check. It is a local demo stack: it uses the `development` environment
and enables `/docs`. Set `PULSEWATCH_ENVIRONMENT=production` and disable docs for
shared deployments. The API runs as an unprivileged user with a read-only filesystem.
Database credentials in `compose.yaml` are development defaults; replace them and
the corresponding `PULSEWATCH_DATABASE_URL` for any shared environment.

### Standalone container

A standalone container needs an external PostgreSQL database:

```bash
docker build -f docker/Dockerfile -t pulsewatch:local .

docker run --rm \
  -e PULSEWATCH_DATABASE_URL='postgresql+asyncpg://user:password@host:5432/pulsewatch' \
  -p 127.0.0.1:8000:8000 \
  --read-only --tmpfs /tmp:size=16m \
  pulsewatch:local
```

Apply migrations before starting the container, or override the command:

```bash
docker run ... pulsewatch:local sh -c 'pulsewatch-migrate && exec pulsewatch'
```

A container has its own disk and network namespaces, so its telemetry differs
from a host-level deployment; see
[docs/deployment.md](docs/deployment.md#container-visibility) before using it
for host monitoring.

### systemd

A hardened unit is provided at
[deploy/systemd/pulsewatch.service](deploy/systemd/pulsewatch.service). It runs
`pulsewatch-migrate` before the API, reads configuration from
`/etc/pulsewatch/pulsewatch.env`, and applies sandboxing directives such as
`ProtectSystem=strict`, `NoNewPrivileges`, and a system-call allow-list.

Run `make verify-unit` to validate the unit against stubbed install paths without
root. The unit is statically verified; it is not installed or started by CI. The
full installation walkthrough, including PostgreSQL setup, migration, and
privilege separation, is in [docs/deployment.md](docs/deployment.md#systemd).

## Project structure

```text
pulsewatch/
├── .github/workflows/ci.yml    # Quality, PostgreSQL integration, container stack
├── deploy/systemd/             # Hardened production unit
├── docker/Dockerfile           # Multi-stage, non-root image
├── docs/
│   ├── api.md                  # Endpoint and error contract
│   ├── architecture.md         # Request, sampling, and storage design
│   ├── deployment.md           # Docker, PostgreSQL, systemd operations
│   └── assets/banner.svg
├── migrations/                 # Alembic environment and versions
├── src/pulsewatch/
│   ├── api/                    # Routes and Pydantic response models
│   ├── collectors/             # psutil collector behind a protocol
│   ├── core/                   # Config, logging, errors, middleware
│   ├── db/                     # Engine, model, repository, typed errors
│   ├── services/               # Background sampler and retention cleanup
│   ├── __main__.py             # `pulsewatch` CLI
│   ├── migrate.py              # packaged `pulsewatch-migrate` CLI
│   └── main.py                 # Application factory and lifespan
├── scripts/                    # Systemd unit verification
├── tests/
│   ├── integration/            # PostgreSQL-backed tests
│   └── test_*.py               # Unit and API tests
├── alembic.ini
├── compose.yaml
├── Makefile
├── pyproject.toml
└── uv.lock
```

## Roadmap

- [x] Application factory, typed settings, structured logging
- [x] CPU, memory, disk, and network collection
- [x] Versioned API, health probes, OpenAPI documentation
- [x] Problem-details error handling and request correlation
- [x] pytest suite, Ruff, mypy, coverage gate, GitHub Actions
- [x] Python packaging and a `pulsewatch` console entrypoint
- [x] Docker image, Compose stack, and hardened systemd unit
- [x] PostgreSQL schema, async repository, and Alembic migration
- [x] Background sampler with configurable interval
- [x] Readiness based on PostgreSQL and sampler freshness
- [x] Historical metric query endpoint with time-range filters
- [x] Retention policy and batched cleanup job
- [x] Static systemd unit verification and local migration workflow
- [x] Typed storage errors, cursor-window binding, and packaged migrations
- [x] Integration-test command and failure-path coverage
- [ ] Production runbook: reverse proxy, TLS, log shipping, backup/restore
- [ ] Load tests and published performance characteristics

## Design decisions

- **One producer.** The background sampler is the only caller of psutil. This
  keeps CPU measurements on a deterministic interval and avoids request-driven
  sampling artifacts.
- **Latest persisted sample.** `/current` reads from the repository instead of
  collecting on demand. It stays fast and consistent with stored history.
- **Keyset history pagination.** Opaque cursors encode collection time, row
  identity, and the originating window, avoiding large offsets and unstable
  pages.
- **Typed failure boundaries.** Repositories translate expected database failures
  into `StorageUnavailableError`; routes map only those to `503` and let bugs
  become `500`s.
- **Batched retention.** Expired rows are deleted in bounded batches to avoid
  long locks and unbounded transactions.
- **Async storage, threaded collection.** SQLAlchemy and asyncpg are async; the
  blocking psutil call runs through `asyncio.to_thread`.
- **Explicit lifecycle.** The sampler and retention service start and stop with
  the FastAPI lifespan. The database engine is disposed during shutdown.
- **Readiness is dependency-aware.** PostgreSQL connectivity and sample freshness
  both matter. A degraded service returns `503` with detailed checks rather than
  a generic server error.
- **Boring, standard packaging.** Hatchling builds a `src/`-layout wheel; uv
  manages reproducible environments; Alembic owns schema evolution.

## Contributing

Issues and pull requests are welcome. Read
[CONTRIBUTING.md](CONTRIBUTING.md) for the local workflow, commit conventions,
and quality gate requirements. For security reports, follow
[SECURITY.md](SECURITY.md) instead of opening a public issue.

## License

Released under the [MIT License](LICENSE).

<div align="center">
  <sub>Built with Python, FastAPI, psutil, PostgreSQL, and a preference for observable systems.</sub>
</div>
