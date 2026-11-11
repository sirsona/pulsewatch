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
> **Project status: early development.** PulseWatch now samples host metrics on a
> fixed cadence, stores them in PostgreSQL, and serves the latest persisted
> snapshot. Historical queries and retention are the next milestone. See the
> [roadmap](#roadmap).

## Overview

PulseWatch runs a single background sampler against the local Linux host,
persists each snapshot in PostgreSQL, and exposes the latest stored sample over a
versioned HTTP API. It is designed to run as a hardened **systemd** service or as
a **Docker Compose** stack.

The service is intentionally built beyond the happy path:

- typed, validated configuration
- one psutil collection path with a fixed sampling interval
- PostgreSQL storage through an async repository
- Alembic-managed schema
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
| Hardened systemd unit | ✅ Included; not installed by CI |
| Historical metrics endpoint | 🚧 Planned |
| Retention policy | 🚧 Planned |

## Architecture

```mermaid
flowchart LR
    client[Operator / probe] -->|JSON over HTTP| api

    subgraph process["PulseWatch process"]
        direction TB
        api[FastAPI app]
        middleware[Request ID + access logs]
        sampler[Background sampler]
        collector[psutil collector]
        repository[Async repository]
        api --> middleware
        sampler --> collector
        sampler --> repository
        api --> repository
    end

    collector -->|/proc, /sys| kernel[(Linux kernel)]
    repository -->|SQLAlchemy + asyncpg| postgres[(PostgreSQL)]
    probes[systemd / Docker healthcheck] --> health[Health probes]
    health --> api

    history[History API] -. planned .-> repository
    retention[Retention job] -. planned .-> postgres
```

Only the sampler calls psutil. It runs immediately at startup and then on the
configured interval, writing each snapshot through the repository. The metrics
endpoint reads the latest stored snapshot rather than triggering another
collection. That gives CPU usage a stable measurement window and keeps API
requests fast.

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

uv run alembic upgrade head
uv run pulsewatch --reload
```

The default configuration expects:

```text
postgresql+asyncpg://pulsewatch:pulsewatch@127.0.0.1:5432/pulsewatch
```

### Run the quality gates

```bash
make check        # Ruff + mypy + pytest with coverage
make test         # pytest only
make lint         # Ruff
make typecheck    # mypy
make migrate      # apply PostgreSQL migrations
```

The suite enforces **85% branch coverage** and currently has **66 tests at
roughly 97% coverage**. CI runs on Python 3.12 and 3.13, runs the PostgreSQL
integration tests, builds the image, and boots the complete Compose stack before
checking readiness and a stored metric.

To run the PostgreSQL integration test locally, apply migrations and provide a
test database URL:

```bash
export PULSEWATCH_DATABASE_URL=postgresql+asyncpg://pulsewatch:pulsewatch@127.0.0.1:5432/pulsewatch_test
export PULSEWATCH_TEST_DATABASE_URL=$PULSEWATCH_DATABASE_URL

uv run alembic upgrade head
uv run pytest -m integration
```

## API

All application endpoints are versioned under `/api/v1`; operational probes are
intentionally unversioned.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Service metadata and links |
| `GET` | `/health/live` | Process liveness probe |
| `GET` | `/health/ready` | PostgreSQL and sampler readiness |
| `GET` | `/api/v1/metrics/current` | Latest persisted host metrics snapshot |
| `GET` | `/docs` | Interactive OpenAPI documentation |
| `GET` | `/openapi.json` | OpenAPI schema |

`/health/ready` returns `200` when the database is reachable and the latest
sample is fresh. It returns `503` with a degraded health body when either check
fails. It does not call psutil.

`/api/v1/metrics/current` returns `503` until the first sample is stored or when
the metrics store is unavailable.

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
| `PULSEWATCH_SAMPLER_ENABLED` | `true` | Set `false` only for API-only tests or maintenance |
| `PULSEWATCH_SAMPLE_INTERVAL_SECONDS` | `15` | Minimum 1 second |
| `PULSEWATCH_SAMPLER_STALE_AFTER_SECONDS` | `45` | Must be at least the sampling interval |

`.env` is ignored by Git. Start from [.env.example](.env.example).

## Deployment

### Docker Compose

```bash
docker compose up --build --detach
docker compose ps
docker compose logs -f pulsewatch
```

The Compose stack includes PostgreSQL with a persistent volume, runs
`alembic upgrade head` before starting the API, and gives the app a readiness
health check. The API runs as an unprivileged user with a read-only filesystem.
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
docker run ... pulsewatch:local sh -c 'alembic upgrade head && exec pulsewatch'
```

A container has its own disk and network namespaces, so its telemetry differs
from a host-level deployment; see
[docs/deployment.md](docs/deployment.md#container-visibility) before using it
for host monitoring.

### systemd

A hardened unit is provided at
[deploy/systemd/pulsewatch.service](deploy/systemd/pulsewatch.service). It runs
`alembic upgrade head` before the API, reads configuration from
`/etc/pulsewatch/pulsewatch.env`, and applies sandboxing directives such as
`ProtectSystem=strict`, `NoNewPrivileges`, and a system-call allow-list.

The full installation walkthrough, including PostgreSQL setup and migration
verification, is in [docs/deployment.md](docs/deployment.md#systemd).

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
│   ├── db/                     # Engine, model, repository
│   ├── services/               # Background sampler
│   ├── __main__.py             # `pulsewatch` CLI
│   └── main.py                 # Application factory and lifespan
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
- [ ] Historical metric query endpoint with time-range filters
- [ ] Retention policy and cleanup job
- [ ] Production runbook: reverse proxy, TLS, log shipping, backup/restore
- [ ] Load tests and published performance characteristics

## Design decisions

- **One producer.** The background sampler is the only caller of psutil. This
  keeps CPU measurements on a deterministic interval and avoids request-driven
  sampling artifacts.
- **Latest persisted sample.** `/current` reads from the repository instead of
  collecting on demand. It stays fast and consistent with stored history.
- **Async storage, threaded collection.** SQLAlchemy and asyncpg are async; the
  blocking psutil call runs through `asyncio.to_thread`.
- **Explicit lifecycle.** The sampler starts and stops with the FastAPI lifespan.
  The database engine is disposed during shutdown.
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
