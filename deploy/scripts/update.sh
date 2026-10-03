#!/usr/bin/env bash
# Update to the latest main (or a given ref) with a backup first; --rollback <ref> restores code
# and offers the pre-update backup. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/../.."
MODE="${1:-update}"; REF="${2:-}"
units() { systemctl list-units --type=service --no-legend 'companion-*' 2>/dev/null | awk '{print $1}'; }
stop_units() { for u in $(units); do sudo systemctl stop "$u"; done; }
start_units() { for u in $(units); do sudo systemctl start "$u"; done; }
if [ "$MODE" = "--rollback" ]; then
  [ -n "$REF" ] || { echo "usage: $0 --rollback <git-ref>" >&2; exit 2; }
  echo "== rolling back code to $REF"; stop_units; git checkout --quiet "$REF"; uv sync --all-packages --frozen; (cd apps/desk && npm ci --no-audit --no-fund && npm run build) || true
  echo "If a migration ran during the update, restore the pre-update backup now: deploy/scripts/restore.sh data/backups/<stamp> --yes"
  start_units; exit 0
fi
echo "== backup before update"; deploy/scripts/backup.sh
BEFORE=$(git rev-parse --short HEAD)
echo "== fetching"; git fetch --quiet origin; TARGET="${REF:-origin/main}"
echo "changes: $(git rev-list --count HEAD.."$TARGET") commit(s)"; git log --oneline HEAD.."$TARGET" | head -20
stop_units
git checkout --quiet "$TARGET" 2>/dev/null || git merge --ff-only "$TARGET"
uv sync --all-packages --frozen
(cd apps/desk && npm ci --no-audit --no-fund && npm run build) || echo "UI build skipped (no npm?)"
uv run --no-sync companion-api migrate
uv run --no-sync companion-api check-config >/dev/null
start_units
echo "updated $BEFORE -> $(git rev-parse --short HEAD). Rollback: $0 --rollback $BEFORE"
