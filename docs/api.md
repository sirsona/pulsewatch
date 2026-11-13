# API contract

PulseWatch exposes an HTTP+JSON API backed by a PostgreSQL metrics store. The
interactive OpenAPI documentation is served at `/docs` and the raw schema at
`/openapi.json` when `PULSEWATCH_DOCS_ENABLED=true`.

- **Default bind:** `127.0.0.1:8000`
- **Application prefix:** `/api/v1`
- **Operational probes:** unversioned, under `/health/`
- **Error media type:** `application/problem+json`
- **Readiness media type:** `application/json`

## Versioning

Application data endpoints live under `/api/v1`. The root discovery endpoint and
operational probes intentionally sit outside the versioned API. Breaking changes
to application data endpoints require a new path version.

## Request correlation

Every response includes the configured correlation header (default
`X-Request-ID`).

- A caller-supplied ID is reused if it matches `^[A-Za-z0-9._:-]{1,128}$`.
- Missing or unsafe IDs are replaced with a generated 32-character hex ID.
- The same ID is included in JSON logs and in error responses as `request_id`.

```bash
curl -i -H 'X-Request-ID: trace-42' http://127.0.0.1:8000/health/live
```

## Endpoints

### `GET /`

Returns service metadata for discovery and smoke tests.

```json
{
  "name": "pulsewatch",
  "version": "0.2.1",
  "environment": "development",
  "documentation": "/docs",
  "health": {
    "live": "/health/live",
    "ready": "/health/ready"
  }
}
```

### `GET /health/live`

Returns `200 OK` whenever the process is alive and able to serve HTTP. It does
not inspect PostgreSQL, the sampler, or host metrics.

```json
{
  "status": "ok",
  "service": "pulsewatch",
  "version": "0.2.1"
}
```

Use this for container and systemd liveness checks. It is intentionally cheap
and should not cause a restart just because a dependency is unavailable.

### `GET /health/ready`

Checks two things:

1. PostgreSQL accepts a trivial query.
2. The sampler has successfully written a sample within
   `PULSEWATCH_SAMPLER_STALE_AFTER_SECONDS`.

It does **not** call psutil.

Ready response — HTTP `200`:

```json
{
  "status": "ok",
  "service": "pulsewatch",
  "version": "0.2.1",
  "checks": {
    "database": "ok",
    "sampler": "ok"
  }
}
```

Degraded responses — HTTP `503`:

```json
{
  "status": "degraded",
  "service": "pulsewatch",
  "version": "0.2.1",
  "checks": {
    "database": "unavailable",
    "sampler": "stale"
  }
}
```

If sampling is disabled, the sampler check is reported as `disabled` and is not
required for readiness. Disabling sampling is intended for tests and maintenance,
not normal operation.

Readiness may return `503` during the first moments after startup until the first
sample has been persisted. Startup ordering and health-check retries should
account for this.

### `GET /api/v1/metrics/current`

Returns the most recent snapshot successfully written by the sampler.

```
Content-Type: application/json
```

It returns `503` when:

- no sample has been stored yet, or
- the metrics repository cannot be reached.

The repository is the source of truth; this endpoint does not invoke psutil.

Fields:

| Object | Field | Meaning |
| --- | --- | --- |
| root | `timestamp` | Collection time, UTC ISO 8601 |
| root | `hostname` | Host reported by the OS |
| root | `platform` | Platform description |
| root | `boot_time` | Boot time, UTC ISO 8601 |
| root | `uptime_seconds` | Seconds since boot |
| `cpu` | `usage_percent` | CPU utilisation over the sampler interval |
| `cpu` | `logical_cores` / `physical_cores` | Core counts |
| `cpu` | `per_core_percent` | Per-logical-core utilisation |
| `cpu` | `load_average_*` | Unix load averages, or `null` if unavailable |
| `memory` | `*_bytes` | Physical memory and swap values |
| `memory` | `usage_percent` | Physical memory utilisation |
| `disk` | `path` | Filesystem reported by `PULSEWATCH_DISK_PATH` |
| `disk` | `*_bytes` / `usage_percent` | Capacity for that path |
| `disk` | `read_bytes` / `write_bytes` | Host-wide cumulative disk I/O |
| `network` | `bytes_*`, `packets_*` | Host-wide cumulative counters |
| `network` | `errors_*`, `drops_*` | Cumulative error and drop counters |

CPU usage is measured between successive sampler runs, not between API requests.
The first sample immediately after process startup may report a near-zero CPU
value because the sampling window is very short. Subsequent samples use the
configured interval.

Cumulative disk and network counters are since boot, not since the previous
sample. Subtract two samples to calculate a rate.

### `GET /api/v1/metrics/history`

Returns a bounded, newest-first page of persisted snapshots.

Query parameters:

| Parameter | Default | Constraints |
| --- | --- | --- |
| `start` | one hour before `end` | Timezone-aware ISO 8601 |
| `end` | now | Timezone-aware ISO 8601 |
| `limit` | `100` | 1–1000 samples per page |
| `cursor` | none | Opaque `next_cursor` from a previous page |

The time window is inclusive, must have `start < end`, and cannot exceed **7
days**. A cursor is bound to its originating window. If `start` and `end` are
omitted while paginating, the cursor’s window is reused; explicitly supplied
values must match it or the request returns `422`.

```bash
curl -G http://127.0.0.1:8000/api/v1/metrics/history \
  --data-urlencode 'start=2026-11-12T08:00:00+00:00' \
  --data-urlencode 'end=2026-11-12T09:00:00+00:00' \
  --data-urlencode 'limit=100'
```

Response:

```json
{
  "start": "2026-11-12T08:00:00Z",
  "end": "2026-11-12T09:00:00Z",
  "limit": 100,
  "count": 0,
  "next_cursor": null,
  "samples": []
}
```

- Samples are ordered newest first.
- `count` is the number of samples in this page.
- `next_cursor` is `null` when there are no more matching samples.
- Pass `next_cursor` back as `cursor` to fetch the next page.
- Cursors are deliberately opaque; do not parse or construct them.
- Invalid or mismatched windows and malformed cursors return `422` problem details.
- An unavailable metrics store returns `503` problem details.

The cleanup task retains samples for `PULSEWATCH_RETENTION_DAYS`, so a history
window that extends beyond retention can be valid but return fewer samples.

### `GET /docs` and `GET /openapi.json`

Interactive documentation and the machine-readable OpenAPI schema. Both return
`404` when docs are disabled, which is recommended for production.

## Errors

Application errors use [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)
problem details:

```json
{
  "type": "about:blank",
  "title": "Service Unavailable",
  "status": 503,
  "detail": "The metrics store is unavailable.",
  "instance": "/api/v1/metrics/current",
  "code": "http_503",
  "request_id": "2f6080eaff4d4f0fbf6a5fce09d6432c"
}
```

| Field | Meaning |
| --- | --- |
| `type` | Always `about:blank` in the current implementation |
| `title` | Short, human-readable summary |
| `status` | HTTP status code |
| `detail` | Context for this occurrence |
| `instance` | Request path |
| `code` | Stable machine-readable identifier |
| `request_id` | Correlation ID, also returned as a response header |
| `errors` | Field-level validation details when status is `422` |

Error codes:

| Code | Status | Cause |
| --- | --- | --- |
| `http_404` | 404 | Route not found |
| `http_405` | 405 | Method not allowed |
| `validation_error` | 422 | Invalid request payload |
| `http_422` | 422 | Invalid history time window or cursor |
| `http_503` | 503 | No sample is available or storage is unavailable |
| `internal_server_error` | 500 | Unhandled server failure |

Readiness is the exception to the problem-details shape: it uses the health
schema shown above so dependency checks remain inspectable. Other 503 responses,
including those from `/api/v1/metrics/current`, use problem details.

Unexpected exceptions return a generic message; internal details and stack
traces remain in the structured server logs and are not leaked to clients.

## Current limitations

- No cross-host or hostname filtering; the service assumes a single monitored
  host.
- No authentication or rate limiting. Keep the service bound to loopback and put
  an authenticated reverse proxy in front before exposing it.
- No CORS policy; browser clients should use a same-origin proxy.
- Linux is the primary target. Some counters may be unavailable on other
  platforms and will be reported as `null` or zero.
