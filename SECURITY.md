# Security policy

## Supported versions

Security fixes are provided for the latest `0.1.x` release and the `main` branch.
Older snapshots are not supported.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's **Security**
tab by opening a
[private vulnerability advisory](https://github.com/sirsona/pulsewatch/security/advisories/new).
Do not open a public issue for a vulnerability.

Include as much of the following as possible:

- affected version or commit
- deployment mode (systemd or container)
- reproduction steps or a proof of concept
- impact assessment
- suggested remediation, if known

Reports are handled on a best-effort basis. There is no bug-bounty programme or
guaranteed response SLA.

## Operational security

PulseWatch exposes host telemetry and is **unauthenticated by design** in its
current early-development state. It is intended to be bound to loopback or put
behind an authenticated, TLS-terminating reverse proxy.

- Never expose port 8000 directly to an untrusted network.
- Set `PULSEWATCH_DOCS_ENABLED=false` in production.
- Run the service as the dedicated unprivileged account, not as root.
- Keep the provided systemd sandboxing or the read-only container flags.
- Treat container host-namespace options (`--pid=host`, `--network=host`, host
  path mounts) as security decisions that require review.
- Do not attach secrets to this service; the current feature set needs none.
- Keep Python dependencies current and review Dependabot updates.

## Threat model

The primary risks considered by this project are:

1. Unintended public exposure of host metadata.
2. Command or data injection through API input.
3. Path traversal or unsafe filesystem access via configuration.
4. Denial of service through expensive endpoints.
5. Privilege escalation from the service account.

Configuration paths are validated, responses are typed, and input surfaces are
limited to query parameters and headers. The only filesystem path read is the
validated `PULSEWATCH_DISK_PATH` plus psutil's OS interfaces. Do not add
endpoints that accept arbitrary paths.

The current API has no authentication, rate limiting, or CORS policy. These are
known limitations and must be handled at the deployment edge.
