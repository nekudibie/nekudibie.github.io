#!/usr/bin/env bash
# Restore vault.db (+ brain.db) from a backup folder. Stops nothing by itself: stop the
# services first (systemctl stop companion-api companion-vault companion-worker).
set -euo pipefail
cd "$(dirname "$0")/../.."
if [ $# -lt 1 ]; then echo "usage: $0 <backup-folder> [--yes]" >&2; exit 2; fi
uv run --no-sync companion-vault restore "$@"
echo "Now start the services again and check /readyz. If search looks stale: uv run companion-vault reindex"
