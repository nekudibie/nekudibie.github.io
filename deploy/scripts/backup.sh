#!/usr/bin/env bash
# Nightly backup for the host that owns vault.db (and brain.db when co-located).
# Uses SQLite's online backup API via `companion-vault backup`; safe while services run.
# Copy the resulting folder to a second disk or host; see docs/OPERATIONS.md.
set -euo pipefail
cd "$(dirname "$0")/../.."
DEST="${COMPANION_BACKUP_DEST:-}"
KEEP="${COMPANION_BACKUP_KEEP:-14}"
ARGS=(--keep "$KEEP")
[ -n "$DEST" ] && ARGS+=(--dest "$DEST")
[ "${COMPANION_BACKUP_INCLUDE_BRAIN:-1}" = "1" ] && ARGS+=(--include-brain)
uv run --no-sync companion-vault backup "${ARGS[@]}"
