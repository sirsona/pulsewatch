# Deployment

PulseWatch has two supported deployment paths:

- **Docker Compose:** API + PostgreSQL, recommended for local evaluation and
  small self-contained deployments.
- **systemd:** the host-native deployment, recommended when full host disk and
  network visibility matters.

Both paths run Alembic migrations before the API starts. Neither path exposes
authentication; keep the API on loopback or behind an authenticated, TLS-enabled
reverse proxy.

## Prerequisites

- Linux host
- Docker 24+ with Compose v2, or Python 3.12+ and PostgreSQL 15+
- A non-root service account for the systemd path
- A database and credentials for the systemd path

## Docker Compose

```bash
docker compose up --build --detach
docker compose ps
docker compose logs -f pulsewatch
```

What happens:

1. PostgreSQL starts with the `pulsewatch-postgres` volume.
2. The API container waits for PostgreSQL's health check.
3. The API command runs `alembic upgrade head`.
4. The sampler writes its first sample immediately.
5. The readiness health check verifies both the database and sampler freshness.

Verify:

```bash
curl --fail --silent http://127.0.0.1:8000/health/ready | python -m json.tool
curl --fail --silent http://127.0.0.1:8000/api/v1/metrics/current | python -m json.tool
curl --fail --silent 'http://127.0.0.1:8000/api/v1/metrics/history?limit=5' | python -m json.tool
```

Stop the stack:

```bash
docker compose down
# Use --volumes to delete the PostgreSQL data as well.
```

The credentials in `compose.yaml` are development defaults. For a shared
environment, override the database password and the API's full
`PULSEWATCH_DATABASE_URL`. URL-encode special characters in passwords.

Compose binds the API to `127.0.0.1`. Set `PULSEWATCH_DOCS_ENABLED=false` before
exposing the service beyond a trusted machine.

## Standalone Docker

A standalone API container requires an external PostgreSQL database. Apply the
migration before starting the API or override the command:

```bash
docker build -f docker/Dockerfile -t pulsewatch:local .

docker run --rm \
  --name pulsewatch \
  --read-only \
  --tmpfs /tmp:size=16m \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  -e PULSEWATCH_DATABASE_URL='postgresql+asyncpg://pulsewatch:password@db-host:5432/pulsewatch' \
  -p 127.0.0.1:8000:8000 \
  pulsewatch:local \
  sh -c 'alembic upgrade head && exec pulsewatch'
```

The image runs as UID/GID `10001` and includes a liveness health check. Compose
overrides it with a readiness check.

### Container visibility

A container has separate mount and network namespaces:

- `disk.path` refers to the container filesystem, not the host's root disk.
- Network counters describe the container network namespace, not host NICs.
- Memory and CPU readings may reflect the host or the container depending on the
  kernel and cgroup setup, but this is not guaranteed.
- Running with `--pid=host` and `--network=host` improves host visibility but
  removes important isolation guarantees. Only do this deliberately.

Use the systemd deployment when accurate host disk and network telemetry is
required.

## systemd

### 1. Create the service account and install the application

```bash
sudo useradd --system --user-group \
  --home-dir /opt/pulsewatch \
  --shell /usr/sbin/nologin \
  pulsewatch

sudo install -d -o pulsewatch -g pulsewatch /opt/pulsewatch

sudo rsync -a --delete \
  --exclude .git \
  --exclude .venv \
  --exclude __pycache__ \
  ./ /opt/pulsewatch/
sudo chown -R pulsewatch:pulsewatch /opt/pulsewatch

sudo -u pulsewatch python3 -m venv /opt/pulsewatch/.venv
sudo -u pulsewatch /opt/pulsewatch/.venv/bin/pip install --no-cache-dir --upgrade pip
sudo -u pulsewatch /opt/pulsewatch/.venv/bin/pip install --no-cache-dir /opt/pulsewatch
```

The entrypoint is `/opt/pulsewatch/.venv/bin/pulsewatch` and Alembic is available
at `/opt/pulsewatch/.venv/bin/alembic`.

### 2. Create the PostgreSQL database

On the database host:

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE pulsewatch LOGIN PASSWORD 'replace-with-a-strong-password';
CREATE DATABASE pulsewatch OWNER pulsewatch;
SQL
```

Restrict network access with PostgreSQL's `pg_hba.conf` and firewall rules. The
application needs only `CONNECT` on its database and DML on its own tables; the
migration account needs schema-change privileges.

### 3. Install configuration

```bash
sudo install -d -m 0750 -o root -g pulsewatch /etc/pulsewatch
sudo install -m 0640 -o root -g pulsewatch \
  .env.example /etc/pulsewatch/pulsewatch.env
sudoedit /etc/pulsewatch/pulsewatch.env
```

Production baseline:

```dotenv
PULSEWATCH_ENVIRONMENT=production
PULSEWATCH_HOST=127.0.0.1
PULSEWATCH_PORT=8000
PULSEWATCH_LOG_LEVEL=INFO
PULSEWATCH_LOG_FORMAT=json
PULSEWATCH_DISK_PATH=/
PULSEWATCH_REQUEST_ID_HEADER=X-Request-ID
PULSEWATCH_DOCS_ENABLED=false
PULSEWATCH_DATABASE_URL=postgresql+asyncpg://pulsewatch:replace-me@127.0.0.1:5432/pulsewatch
PULSEWATCH_SAMPLER_ENABLED=true
PULSEWATCH_SAMPLE_INTERVAL_SECONDS=15
PULSEWATCH_SAMPLER_STALE_AFTER_SECONDS=45
PULSEWATCH_RETENTION_ENABLED=true
PULSEWATCH_RETENTION_DAYS=7
PULSEWATCH_RETENTION_CLEANUP_INTERVAL_SECONDS=3600
PULSEWATCH_RETENTION_BATCH_SIZE=1000
```

The database URL is treated as a secret by the application. It still lives in a
root-readable environment file and must be protected accordingly.

### 4. Install and start the unit

Verify the unit syntax locally before installing it:

```bash
make verify-unit
```

Then install:

```bash
sudo install -m 0644 deploy/systemd/pulsewatch.service \
  /etc/systemd/system/pulsewatch.service
sudo systemctl daemon-reload
sudo systemctl enable --now pulsewatch
```

The unit has an `ExecStartPre` that applies migrations before the API starts.
Verify:

```bash
systemctl status pulsewatch --no-pager
curl --fail --silent http://127.0.0.1:8000/health/ready
journalctl -u pulsewatch -n 30 --no-pager
systemd-analyze security pulsewatch.service
```

If the database is unreachable or the migration fails, the service fails and
systemd retries according to the unit's restart policy. Fix the dependency rather
than bypassing the migration.

### 5. Reverse proxy

Do not expose port 8000 directly to the internet. Terminate TLS and authenticate
at a reverse proxy. Example Nginx location:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Request-ID $request_id;
    proxy_read_timeout 30s;
}
```

Add authentication such as `auth_basic` or an identity-aware proxy. A public
PulseWatch instance reveals hostnames, capacity, load, and network volumes.

## Operations

### Health probes

| Probe | Endpoint | Use |
| --- | --- | --- |
| Liveness | `/health/live` | Restart decision; cheap, process-only |
| Readiness | `/health/ready` | Traffic acceptance; database + sampler freshness |
| Metrics smoke test | `/api/v1/metrics/current` | Confirm persisted telemetry |

Readiness can return `503` for the first few seconds after startup while the
first sample is persisted. Health-check retries should allow for this.

### Migrations

Apply manually:

```bash
# Docker Compose
docker compose run --rm pulsewatch alembic upgrade head

# systemd (loads the same environment file as the unit)
sudo -u pulsewatch sh -c 'set -a; . /etc/pulsewatch/pulsewatch.env; set +a; /opt/pulsewatch/.venv/bin/alembic upgrade head'
```

Check the current revision:

```bash
docker compose run --rm pulsewatch alembic current
sudo -u pulsewatch sh -c 'set -a; . /etc/pulsewatch/pulsewatch.env; set +a; /opt/pulsewatch/.venv/bin/alembic current'
```

Before upgrading across schema changes:

1. Back up the database.
2. Review the migration in `migrations/versions/`.
3. Apply the migration.
4. Start the new application version.
5. Verify readiness and a newly stored sample.

### Backups

Docker Compose:

```bash
docker compose exec -T postgres \
  pg_dump -U pulsewatch -d pulsewatch -Fc > "pulsewatch-$(date +%F).dump"
```

Restore into an empty database:

```bash
docker compose exec -T postgres \
  pg_restore -U pulsewatch -d pulsewatch --clean --if-exists < pulsewatch-2026-11-11.dump
```

For host PostgreSQL, use the same `pg_dump`/`pg_restore` commands with your
connection parameters. Store backups outside the data volume and test restores.

### Logs

The service writes one JSON object per line to stderr. Under systemd:

```bash
journalctl -u pulsewatch -f -o cat
journalctl -u pulsewatch -o cat | jq 'select(.level == "error")'
```

Under Compose:

```bash
docker compose logs -f pulsewatch
docker compose logs --no-log-prefix pulsewatch | jq -c .
```

### Configuration changes

```bash
sudoedit /etc/pulsewatch/pulsewatch.env
sudo systemctl restart pulsewatch
```

Database URL, sampling interval, stale threshold, bind address, port, and disk
path changes require a restart. Invalid configuration prevents startup.

### Upgrades and rollback

1. Read the release notes and back up PostgreSQL.
2. Fetch the new release.
3. Re-run the systemd installation/rsync steps, including the ownership fix, and
   reinstall into the virtualenv.
4. Restart the service; `ExecStartPre` applies pending migrations.
5. Verify `/health/ready` and confirm new samples are being written.
6. If the release fails, redeploy the previous tag. Restore the database backup
   only when a migration is not backward-compatible.

For containers, deploy immutable version tags rather than `latest`. Roll back
the image tag first; database restore is a last resort.

### Capacity

The current service is a single application process with one sampler. No load or
capacity benchmark has been published. Size PostgreSQL storage from:

```text
row_size ≈ full metric snapshot payload
rows_per_day ≈ 86400 / PULSEWATCH_SAMPLE_INTERVAL_SECONDS
retained_rows ≈ rows_per_day × PULSEWATCH_RETENTION_DAYS
```

At the default 15-second interval and 7-day retention, that is about 5,760 rows
per host per day and roughly 40,320 retained rows. Row size depends on the JSON
payload, indexes, and PostgreSQL overhead; measure your own database before
sizing long-term storage.

Retention runs hourly by default and deletes in batches. Cleanup failures are
logged as `retention cleanup failed`; they do not change readiness, so monitor
that log event and table size separately.

## Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Service exits with validation error | Missing or invalid database URL, disk path, or sampling settings | Fix `/etc/pulsewatch/pulsewatch.env`; check `journalctl` |
| `/health/ready` returns `503` with `database: unavailable` | PostgreSQL down, credentials wrong, or network blocked | Check `pg_isready`, credentials, and firewall |
| `/health/ready` returns `503` with `sampler: stale` | Sampler cannot write samples | Inspect `metric sampling failed` logs and database disk space |
| `/api/v1/metrics/current` returns `503` immediately after startup | No sample has been persisted yet | Wait for the first sample; check sampler logs |
| History returns `422` | Window is naive, reversed, longer than 7 days, or the cursor is malformed | Use timezone-aware timestamps and reuse the returned cursor |
| Retention logs failures | Database error, lock timeout, or insufficient privileges | Check PostgreSQL health and logs; adjust batch size if needed |
| Migration fails with permission denied | Database role lacks schema privileges | Grant ownership or DDL privileges to the migration role |
| Compose API restarts repeatedly | Migration or database connection failure | `docker compose logs pulsewatch`, then verify PostgreSQL health |
| Disk or network metrics describe the container | Container namespace isolation | Use systemd or review host namespace trade-offs |
| Port 8000 already in use | Another process is bound to the port | Change `PULSEWATCH_PORT` or stop the conflict |

## Security checklist

- [ ] Keep the API bound to loopback or behind an authenticated proxy.
- [ ] Set `PULSEWATCH_DOCS_ENABLED=false` in production.
- [ ] Run as the dedicated `pulsewatch` user, never root.
- [ ] Use the provided systemd hardening or the read-only container flags.
- [ ] Treat `PULSEWATCH_DATABASE_URL` as a secret.
- [ ] Restrict database network access and grant least privilege.
- [ ] Back up and test restore procedures before schema upgrades.
- [ ] Do not mount host paths or enable host namespaces without review.
- [ ] Keep dependencies current via Dependabot and reviewed upgrades.
- [ ] Protect and rotate proxy credentials and TLS material separately.
