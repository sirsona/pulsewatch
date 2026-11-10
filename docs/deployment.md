# Deployment

PulseWatch supports two first-class deployment paths:

- **systemd** on a Linux host, which has full visibility into the host's disks,
  network interfaces, and `/proc`.
- **Docker/Compose**, which provides a reproducible, unprivileged container but
  is constrained by container namespaces.

This document covers installation, configuration, operation, and the security
model. The recommended production path for host monitoring is systemd.

## Prerequisites

- Linux with systemd (for the systemd path) or Docker 24+ with Compose v2
- Python **3.12+** for the systemd path
- A non-root service account
- Optional: a TLS-terminating reverse proxy with authentication

The API itself has no authentication. Keep `PULSEWATCH_HOST=127.0.0.1` and place
an authenticated proxy in front if remote access is required.

## Container

Build the image from the repository root:

```bash
docker build -f docker/Dockerfile -t pulsewatch:0.1.0 .
```

Run it with a read-only root filesystem and an unprivileged user:

```bash
docker run --rm \
  --name pulsewatch \
  --read-only \
  --tmpfs /tmp:size=16m \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  -p 127.0.0.1:8000:8000 \
  pulsewatch:0.1.0
```

The image already runs as UID/GID `10001` and includes a health check against
`/health/live`.

### Compose

```bash
docker compose up --build --detach
docker compose ps
docker compose logs -f pulsewatch
```

The provided `compose.yaml` binds to loopback, drops all capabilities, uses a
read-only filesystem, and sets memory and PID limits. Override settings in a
`compose.override.yaml` rather than editing the committed file for local
preferences.

### Container visibility

A container has separate mount and network namespaces:

- `disk.path` refers to the container filesystem, not the host's root disk.
- Network counters describe the container's network namespace and virtual
  interfaces, not the host's physical NICs.
- Memory and CPU readings can reflect the host, depending on the kernel and
  cgroup version, but are not guaranteed to be host-wide.
- Running with `--pid=host` and `--network=host` improves host visibility but
  removes important isolation guarantees. Only do so deliberately, with a
  reviewed configuration.

Use the systemd deployment when accurate host disk and network telemetry is
required.

## systemd

### 1. Create the service account and directories

```bash
sudo useradd --system --user-group \
  --home-dir /opt/pulsewatch \
  --shell /usr/sbin/nologin \
  pulsewatch

sudo install -d -o pulsewatch -g pulsewatch /opt/pulsewatch
```

### 2. Install the application

From the repository root:

```bash
sudo rsync -a --delete \
  --exclude .git \
  --exclude .venv \
  --exclude __pycache__ \
  ./ /opt/pulsewatch/

sudo -u pulsewatch python3 -m venv /opt/pulsewatch/.venv
sudo -u pulsewatch /opt/pulsewatch/.venv/bin/pip install \
  --no-cache-dir --upgrade pip
sudo -u pulsewatch /opt/pulsewatch/.venv/bin/pip install \
  --no-cache-dir /opt/pulsewatch
```

The console entrypoint is now
`/opt/pulsewatch/.venv/bin/pulsewatch`.

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
```

`PULSEWATCH_DISK_PATH` must exist and be a directory; startup fails fast
otherwise.

### 4. Install and start the unit

```bash
sudo install -m 0644 deploy/systemd/pulsewatch.service \
  /etc/systemd/system/pulsewatch.service
sudo systemctl daemon-reload
sudo systemctl enable --now pulsewatch
```

Verify:

```bash
systemctl status pulsewatch --no-pager
curl --fail --silent http://127.0.0.1:8000/health/ready
journalctl -u pulsewatch -n 20 --no-pager
systemd-analyze security pulsewatch.service
```

The unit applies `ProtectSystem=strict`, `PrivateDevices`, `NoNewPrivileges`, an
empty capability set, and the `@system-service` system-call allow-list. If you
need to change `PULSEWATCH_PORT` or bind to a different interface, update
`/etc/pulsewatch/pulsewatch.env`, not the unit.

### 5. Reverse proxy (optional)

Terminate TLS and authenticate at a reverse proxy. Example Nginx location:

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

Do not expose port 8000 directly to the internet. A public PulseWatch instance
reveals hostnames, capacity, load, and network volumes.

## Operations

### Health probes

| Probe | Endpoint | Use |
| --- | --- | --- |
| Liveness | `/health/live` | Restart decision; must stay cheap |
| Readiness | `/health/ready` | Traffic acceptance; checks the collector |
| Metrics smoke test | `/api/v1/metrics/current` | Confirm real telemetry |

Do not point a load balancer at `/health/live` as a readiness signal. The
distinction matters once persistence is added.

### Logs

The service writes one JSON object per line to stderr. Under systemd, logs go to
the journal:

```bash
journalctl -u pulsewatch -f -o cat
journalctl -u pulsewatch -o cat | jq 'select(.level == "error")'
```

Under Docker:

```bash
docker compose logs -f pulsewatch
docker compose logs --no-log-prefix pulsewatch | jq -c .
```

Set a Docker log driver or journald retention policy appropriate to your host.
No log files are written by the application.

### Configuration changes

```bash
sudoedit /etc/pulsewatch/pulsewatch.env
sudo systemctl restart pulsewatch
```

Changing `PULSEWATCH_HOST`, `PULSEWATCH_PORT`, or `PULSEWATCH_DISK_PATH`
requires a restart. Invalid configuration prevents startup rather than serving
with partial settings.

### Upgrades

1. Fetch the desired tag/release.
2. Re-run the rsync and `pip install` steps.
3. Restart the service.
4. Verify `/health/ready` and inspect logs.
5. If the readiness check fails, redeploy the previous tag and restart.

Docker deployments should use immutable image tags (version or digest), not
`latest`.

### Capacity

The current service is stateless and request-driven. It does not persist data or
run a sampler, so its footprint is small. No benchmark has been published yet;
do not size a production deployment from an assumed number. The planned
persistence and sampling milestone will add explicit memory and database limits.

## Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Service exits at startup with validation error | `PULSEWATCH_DISK_PATH` missing, not a directory, or invalid port | Fix the environment file; check `journalctl` |
| `500` from `/api/v1/metrics/current` | psutil cannot read host metrics | Inspect the `request failed` log entry and traceback |
| `502` from reverse proxy | Service bound to loopback but proxy in another namespace/container | Run the proxy on the host or adjust the bind/reachability model |
| Health check passes but metrics are container-scoped | Docker namespace isolation | Use systemd for host telemetry or review the namespace trade-off |
| Port already in use | Another process bound the port | Change `PULSEWATCH_PORT` or stop the conflicting service |

## Security checklist

- [ ] Keep the API bound to loopback or an authenticated proxy.
- [ ] Set `PULSEWATCH_DOCS_ENABLED=false` in production.
- [ ] Run as the dedicated `pulsewatch` user, never root.
- [ ] Use the provided systemd hardening or the read-only container flags.
- [ ] Do not mount host paths or enable host namespaces without review.
- [ ] Keep dependencies current via Dependabot and reviewed upgrades.
- [ ] Protect and rotate proxy credentials and TLS material separately.
