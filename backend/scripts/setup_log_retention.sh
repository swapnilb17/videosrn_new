#!/usr/bin/env bash
# One-time EC2/host setup: limit systemd journal size and age (default 7 days + 512MB).
# Run from anywhere: sudo ./scripts/setup_log_retention.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONF_SRC="$REPO_ROOT/deploy/journald-retention.conf"

if [[ ! -f "$CONF_SRC" ]]; then
  echo "Missing $CONF_SRC" >&2
  exit 1
fi

if [[ "${EUID:-}" -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi

mkdir -p /etc/systemd/journald.conf.d
install -m 0644 "$CONF_SRC" /etc/systemd/journald.conf.d/99-avatar-retention.conf

# Backup: weekly vacuum (journald usually enforces MaxRetentionSec; this trims edge cases)
cat >/etc/cron.weekly/avatar-journal-vacuum <<'EOF'
#!/bin/sh
/usr/bin/journalctl --vacuum-time=7d >/dev/null 2>&1 || true
EOF
chmod +x /etc/cron.weekly/avatar-journal-vacuum

systemctl restart systemd-journald

echo "Installed journal retention (7 days, 512M max). Current journal disk use:"
journalctl --disk-usage || true
