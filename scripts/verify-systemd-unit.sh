#!/usr/bin/env bash
# Verify the systemd unit syntax and paths without installing it on the host.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_path="${1:-$repo_root/deploy/systemd/pulsewatch.service}"

if ! command -v systemd-analyze >/dev/null 2>&1; then
  echo "systemd-analyze is required for unit verification" >&2
  exit 1
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

install_dir="$tmpdir/opt/pulsewatch"
config_dir="$tmpdir/etc/pulsewatch"
mkdir -p "$install_dir/.venv/bin" "$config_dir"

printf '#!/bin/sh\nexit 0\n' >"$install_dir/.venv/bin/pulsewatch"
printf '#!/bin/sh\nexit 0\n' >"$install_dir/.venv/bin/pulsewatch-migrate"
chmod +x "$install_dir/.venv/bin/pulsewatch" "$install_dir/.venv/bin/pulsewatch-migrate"
printf 'PULSEWATCH_ENVIRONMENT=test\n' >"$config_dir/pulsewatch.env"
chmod 0640 "$config_dir/pulsewatch.env"

sed \
  -e "s|/opt/pulsewatch|$install_dir|g" \
  -e "s|/etc/pulsewatch/pulsewatch.env|$config_dir/pulsewatch.env|g" \
  "$unit_path" >"$tmpdir/pulsewatch.service"

systemd-analyze verify "$tmpdir/pulsewatch.service"
echo "systemd unit syntax verified: $unit_path"
