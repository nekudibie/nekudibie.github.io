# Operations

## Start / stop
* Development: `./deploy/scripts/dev.sh` (Ctrl-C stops). Separate processes:
  `uv run companion-api serve`, `uv run companion-vault serve`, `uv run companion-worker run`.
* Production: systemd units in `deploy/systemd/` (`systemctl --user` or system scope);
  Home Assistant and Ollama via `deploy/compose/`.

## Health
| Endpoint | Meaning |
|---|---|
| `GET /healthz` | process is up |
| `GET /readyz` | vault + brain DB reachable (model may be down; then the UI says "model offline") |
| `GET /version` | version, git sha, Python, platform |
| `GET /v1/status` (auth) | per-dependency status with latency |

## Logs
JSON lines on stderr (`logging.format: json`), with `request_id` and `client_id`. Secrets are
redacted by the formatter; private content is never logged. With systemd: `journalctl -u companion-api -f`.

## Configuration changes
Edit `config/local.yaml` and `.env`, then `uv run companion-api check-config`, then restart.
Changing a client token means editing `.env` and restarting; the old token stops working
immediately after restart.

## Secure access
* Keep `api.host: 127.0.0.1` unless the desk is another machine. For LAN access either:
  * put the API behind a reverse proxy with TLS (Caddy with an internal CA is the simplest), or
  * use a VPN/overlay such as WireGuard or Tailscale and bind to that interface only.
* Browser microphone capture requires HTTPS or localhost; the kiosk Pi should use the native
  audio client instead of browser capture.
* Never expose ports 8710/8720/11434/8123 to the internet.

## Backup and restore
* `deploy/scripts/backup.sh` takes consistent SQLite backups via the backup API (safe while
  running) into `data/backups/<timestamp>/` and prunes old sets. Copy that directory to a
  second disk/host.
* Restore: stop the services, copy `vault.db`/`brain.db` back, start, then run
  `companion-vault reindex` if the index looks stale.
* Deleting a record removes it from the live database at once; backups made before the
  deletion still contain it until they rotate (default retention: 14 daily sets).

## Export and deletion
* `GET /v1/memory/export` (owner/desk) streams every record as JSON lines.
* `DELETE /v1/memory/documents/{id}` removes text and index entries and keeps a tombstone
  (title, hash, timestamps) for audit. `companion-vault stats` shows tombstone counts.

## Email (Gmail, read-only) — Milestone 7
Documented when implemented: creating a Desktop OAuth client, `gmail.readonly` scope, local
loopback consent flow, encrypted token file, revoke procedure.

## Updates and rollback
`git pull && uv sync --all-packages --frozen && (cd apps/desk && npm ci && npm run build)`,
then run migrations (`companion-api migrate`) and restart. Roll back by checking out the
previous tag and restoring the pre-update backup set if a migration was applied.
