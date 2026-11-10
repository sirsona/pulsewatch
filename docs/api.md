# API contract

PulseWatch exposes an HTTP+JSON API. The interactive OpenAPI documentation is
served at `/docs` and the raw schema at `/openapi.json` when
`PULSEWATCH_DOCS_ENABLED=true`.

- **Default bind:** `127.0.0.1:8000`
- **Application prefix:** `/api/v1`
- **Operational probes:** unversioned, under `/health/`
- **Error media type:** `application/problem+json`

## Versioning

Application endpoints live under `/api/v1`. Breaking changes require a new
path version. Operational probes intentionally sit outside the versioned API so
that orchestrators do not need to change their configuration when the API
version advances.

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
  "version": "0.1.0",
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
not inspect dependencies or collect metrics.

```json
{
  "status": "ok",
  "service": "pulsewatch",
  "version": "0.1.0"
}
```

Use this for container and systemd liveness checks. Do not use it as a signal
that the service can handle real traffic.

### `GET /health/ready`

Returns `200 OK` when the collector can produce a snapshot. This endpoint
currently invokes the collector, so it is slightly more expensive than the
liveness probe. When PostgreSQL-backed history is added, it will also check the
database before reporting ready.

```json
{
  "status": "ok",
  "service": "pulsewatch",
  "version": "0.1.0",
  "checks": {
    "api": "ok",
    "collector": "ok"
  }
}
```

### `GET /api/v1/metrics/current`

Returns a point-in-time snapshot of host telemetry.

```
Content-Type: application/json
```

Fields:

| Object | Field | Meaning |
| --- | --- | --- |
| root | `timestamp` | Collection time, UTC ISO 8601 |
| root | `hostname` | Host reported by the OS |
| root | `platform` | Platform description |
| root | `boot_time` | Boot time, UTC ISO 8601 |
| root | `uptime_seconds` | Seconds since boot |
| `cpu` | `usage_percent` | CPU utilisation since the previous poll |
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

`cpu.usage_percent` is calculated between consecutive collector calls. With the
current request-driven design, that interval is the time between API requests;
the planned background sampler will make the interval deterministic.

Cumulative disk and network counters are since boot, not since the previous
request. Subtract two samples to calculate a rate.

### `GET /docs` and `GET /openapi.json`

Interactive documentation and the machine-readable OpenAPI schema. Both return
`404` when docs are disabled (recommended in production).

## Errors

All HTTP errors use [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem
details:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Not Found",
  "instance": "/missing",
  "code": "http_404",
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
| `internal_server_error` | 500 | Unhandled server or collector failure |

Unhandled exceptions return a generic message; internal details and stack traces
remain in the structured server logs and are not leaked to clients.

## Current limitations

- No authentication or rate limiting. Keep the service bound to loopback and put
  an authenticated reverse proxy in front before exposing it.
- No historical queries yet. Each request returns a live snapshot.
- No CORS policy; browser clients should use a same-origin proxy.
- Linux is the primary target. Some counters may be unavailable on other
  platforms and will be reported as `null` or zero.
