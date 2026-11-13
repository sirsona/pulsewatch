# Architecture

## Goals

PulseWatch is a small, reliable Linux monitoring service built to demonstrate
production-oriented Python without obscuring operational detail. Its priorities
are:

1. **Deterministic host telemetry** with psutil as the only sampling source.
2. **Durable samples** in PostgreSQL with a reproducible schema.
3. **A stable HTTP contract** that is easy to consume and operate.
4. **Observable failure** through structured logs, correlation IDs, and
   dependency-aware readiness.
5. **Testability** through explicit application composition and test doubles.

## Current components

```mermaid
flowchart TD
    subgraph client["Clients and operators"]
        operator[curl / probe / dashboard]
    end

    subgraph app["PulseWatch process"]
        mw[RequestContextMiddleware]
        routes[FastAPI routes]
        schemas[Pydantic contracts]
        sampler[SamplerService]
        retention[RetentionService]
        collector[SystemMetricsCollector]
        repo[SqlAlchemyMetricRepository]
        config[Settings]
        logging[JSON logging]
        errors[Problem-details handlers]
    end

    operator -->|HTTP| mw
    mw --> routes
    routes --> schemas
    routes --> repo
    routes --> errors
    sampler --> collector
    sampler --> repo
    retention --> repo
    collector --> proc[/proc, /sys/]
    repo --> postgres[(PostgreSQL)]
    config --> app
    mw --> logging
```

| Module | Responsibility |
| --- | --- |
| `pulsewatch.main` | Composition root, lifespan, route registration |
| `pulsewatch.core.config` | Environment/.env parsing and validation |
| `pulsewatch.core.logging` | JSON/console formatting, request context |
| `pulsewatch.core.middleware` | Request IDs, access logs, last-resort error boundary |
| `pulsewatch.core.errors` | RFC 9457 responses and framework exception handlers |
| `pulsewatch.api` | Route definitions and response schemas |
| `pulsewatch.collectors` | Collector protocol and psutil implementation |
| `pulsewatch.db` | Async engine, SQLAlchemy model, repository |
| `pulsewatch.services.sampler` | Fixed-cadence collection loop |
| `pulsewatch.services.retention` | Batched expired-sample cleanup |
| `pulsewatch.api.cursors` | Window-bound history pagination cursors |
| `pulsewatch.migrate` | Packaged migration entrypoint |
| `migrations` | Alembic environment and schema versions |

## Startup and shutdown

The FastAPI lifespan owns long-lived resources:

1. `create_app()` constructs the database engine, repository, collector, sampler,
   and retention service. Creating an engine does not open a database connection.
2. On startup, the sampler task is created. It attempts its first collection
   immediately. The retention task also starts and runs an initial cleanup.
3. On shutdown, both stop events are set and their tasks are awaited.
4. The database engine is disposed.

If PostgreSQL is unavailable at startup, the API still starts; sampling fails,
`/health/ready` reports degraded, and the sampler retries on the next interval.
In Compose, the app waits for PostgreSQL and runs Alembic before startup, so this
scenario is primarily relevant to dependency loss after startup.

## Sampling lifecycle

The sampler is the **only component that collects metrics**. The collector
primes its CPU counters once during construction:

```text
collector.collect() (worker thread)
        ↓
repository.save_snapshot() (async PostgreSQL write)
        ↓
last_success_at updated
        ↓
wait for interval or shutdown
```

Details:

- psutil is blocking, so collection runs through `asyncio.to_thread`.
- The loop subtracts collection/write time from the interval to avoid drift.
- Write failures are logged with a traceback and do not terminate the task.
  Readiness turns stale after the configured freshness window.
- The first sample uses a very short CPU measurement window; subsequent samples
  use the configured interval.
- The sampler is a single in-process task. Running multiple API workers would
  create one sampler per worker and duplicate writes; this is why the current
  deployment model is one application process.

## Request lifecycle

1. Uvicorn accepts the HTTP connection.
2. `RequestContextMiddleware` resolves or generates a request ID and starts a
   timer.
3. FastAPI routes the request.
4. Metrics routes read the latest stored sample or a bounded history page from
   the repository. Health routes query the repository or sampler state. No route
   calls psutil.
5. Pydantic serialises the response.
6. The middleware adds the request ID header and writes an access log.
7. Unexpected exceptions become a generic `500` problem response; known
   framework and validation errors use dedicated handlers.

## Persistence

The `metric_samples` table stores one row per snapshot:

- Identity primary key
- UTC `collected_at`
- Hostname
- Scalar CPU, memory, and disk percentages for future filtering and aggregation
- Full snapshot payload as `JSONB`

Indexes:

- `collected_at`
- `(hostname, collected_at)`

The model is in `pulsewatch.db.models`; the repository hides SQLAlchemy from the
API. PostgreSQL is the production target, while SQLite covers fast repository
tests. Production JSON is stored as `JSONB`; the model uses a JSON variant so the
same repository logic can run against SQLite in tests.

Alembic owns the schema. The application does not call `create_all()` at
startup. Compose and the systemd unit run `pulsewatch-migrate` before starting the
app. Local development should use `make run`, which applies migrations before
starting the API.

The wheel contains the Alembic scripts under `pulsewatch/migrations`, and the
`pulsewatch-migrate` entrypoint locates them without requiring a working directory
with `alembic.ini`. The sdist includes the deployment and documentation assets.

## History and retention

`GET /api/v1/metrics/history` applies a bounded, inclusive UTC window (maximum
seven days) and returns newest-first samples with cursor pagination. The cursor
encodes the collection timestamp, row identity, and originating window. The next
query uses a strict keyset condition, avoiding large offsets; omitting start/end
reuses the bound window, while a mismatched explicit window is rejected.
Malformed or unsupported cursors are rejected with `422`.

`RetentionService` runs in the application lifespan. Every cleanup:

1. Computes a cutoff from `PULSEWATCH_RETENTION_DAYS`.
2. Selects a bounded batch of old row IDs.
3. Deletes that batch.
4. Repeats until a batch is smaller than the configured batch size.

Batched deletes avoid long locks and unbounded transactions. Cleanup failures are
logged and retried on the next interval; they do not make the API unready.

## Readiness semantics

Readiness validates:

- Database connectivity through `SELECT 1`.
- Sampler freshness: a successful write within the stale threshold.

It deliberately does not call psutil. Readiness may be `503` briefly after
startup before the first sample is stored. Liveness remains a process-only check
so a database outage does not trigger pointless restarts.

Readiness returns the health schema with per-dependency checks and status `503`
when degraded. Other API failures use problem details.

## Logging

Logs are JSON by default, one object per line on stderr:

```json
{
  "timestamp": "2026-11-11T16:48:27.697043+00:00",
  "level": "info",
  "logger": "pulsewatch",
  "message": "request completed",
  "request_id": "trace-42",
  "http_method": "GET",
  "path": "/api/v1/metrics/current",
  "client_ip": "127.0.0.1",
  "status_code": 200,
  "duration_ms": 4.18
}
```

Uvicorn's server and error loggers are redirected through the root handler.
Uvicorn's access logger is suppressed because the middleware emits richer access
entries. Errors include formatted tracebacks in the `exception` field. Local
development can opt into console output with
`PULSEWATCH_LOG_FORMAT=console`.

Database URLs are held as `SecretStr` and are not included in application
configuration representations.

## Error handling

Three layers:

1. Framework HTTP exceptions and request-validation errors are converted by
   registered handlers.
2. Repositories translate expected database failures into
   `StorageUnavailableError`. The metrics and readiness routes map only that
   typed failure to `503`; invalid history windows and cursors return `422`.
3. Unexpected exceptions are not swallowed by request handlers. They reach the
   request middleware, are logged once with a traceback, and become a generic
   `500` problem response.

## Testing strategy

- Route tests use a fake repository and collector; they do not require a
  database.
- Sampler and retention tests use fake collectors/repositories and a real asyncio
  loop.
- Cursor tests cover round-tripping, timezone normalisation, and malformed input.
- Repository tests run against SQLite for fast coverage of query, pagination,
  JSON round-tripping, and batched deletion.
- PostgreSQL integration tests run against a migrated database when
  `PULSEWATCH_TEST_DATABASE_URL` is set; CI provides a PostgreSQL service.
- The container CI job builds the image and starts the real Compose stack,
  checking migration, readiness, current metrics, and history.
- CI installs the built wheel in a clean virtualenv and verifies that the
  packaged migration entrypoint is available.
- `scripts/verify-systemd-unit.sh` checks the unit against stubbed install paths
  without requiring root and fails if `systemd-analyze` is unavailable.
- Wheel-install checks verify that packaged migration scripts are present and
  usable without a repo checkout.

## Next design steps

- Multi-process safety or a dedicated sampler process if scaling beyond one
  application worker.
- Authentication and rate limiting at the edge if the API is exposed beyond
  loopback.
- Backup/restore automation and load testing.
- Optional aggregate endpoints for long time ranges.
