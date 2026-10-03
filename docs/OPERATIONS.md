# Operations

## Start / stop
* Development: `./deploy/scripts/dev.sh` (Ctrl-C stops). Separate processes:
  `uv run companion-api serve`, `uv run companion-vault serve`, `uv run companion-worker run`.
* Production: `deploy/scripts/install-units.sh <role> --enable` installs hardened systemd
  units (`companion-api`, `companion-worker` at lower CPU/IO priority, `companion-vault`,
  `companion-backup.timer`; the desk's `companion-audio` is a user unit). Home Assistant and
  Ollama via `deploy/compose/`. Shut down with `sudo systemctl stop companion-worker companion-api`
  (the worker gets 90 s to finish a chunk; jobs resume after restart).
* Load priority: the worker runs with `Nice=10` and best-effort IO; the queue keeps a slot for
  interactive jobs; Ollama is set to one loaded model and one parallel request so a background
  summary cannot evict the chat model.

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

## Home Assistant
* Create a long-lived access token in HA (Profile → Security) for a dedicated HA user with
  the least rights you can give it; put it in `.env` as `COMPANION_HA_TOKEN`.
* `home.allowed_entities` is an explicit list. Nothing outside it is visible or controllable,
  whatever the model asks. Use `GET /v1/home/discover` with the admin token to see ids.
* Cameras: the UI fetches `/v1/home/cameras/{id}/snapshot` with its client token, or opens the
  MJPEG proxy with a 60-second ticket from `POST /v1/home/cameras/{id}/stream-ticket`. HA
  credentials never reach the browser.

## Jobs and meetings
* `uv run companion-worker list` shows recent jobs and counts; `retry <job_id>` /
  `cancel <job_id>` act on one. In development the worker runs inside the API
  (`worker.embedded: true`); on real hosts run `companion-worker run` as its own service.
* A crashed worker leaves jobs with an expired lease; they are re-queued automatically with
  their attempt count intact. Transcription resumes from the last completed chunk.
* Meeting audio lives under `data/brain/media/recordings/<id>/chunk_*.wav`; transcripts and
  summaries are vault documents (`meeting_transcript`, `meeting_summary`). Deleting a recording
  (`DELETE /v1/meetings/{id}`) removes the audio, segments and both documents; backups rotate
  on their own schedule.
* Employer material: use the `employer_approved` route only where recording is permitted by
  the employer; the route is stored with the recording so it can be audited.

## Secure access
* Keep `api.host: 127.0.0.1` unless the desk is another machine. For LAN access either:
  * put the API behind a reverse proxy with TLS (Caddy with an internal CA is the simplest), or
  * use a VPN/overlay such as WireGuard or Tailscale and bind to that interface only.
* Browser microphone capture requires HTTPS or localhost; the kiosk Pi should use the native
  audio client instead of browser capture.
* Never expose ports 8710/8720/11434/8123 to the internet.

## Backup and restore
* `deploy/scripts/backup.sh` (or `uv run companion-vault backup --include-brain`) takes
  consistent SQLite backups via the online backup API (safe while services run) into
  `data/backups/<UTC timestamp>/` with a `manifest.json` (SHA-256 per file, schema version),
  and prunes to the newest 14 sets. Copy that directory to a second disk or host (rsync).
  Suggested schedule: a systemd timer or cron entry at 02:00.
* Restore: stop the services, then `deploy/scripts/restore.sh data/backups/<stamp> --yes`.
  The copy is checksum- and integrity-checked first; the live files are renamed to
  `*.pre-restore-<stamp>` rather than deleted. Start the services, check `/readyz`, and run
  `uv run companion-vault reindex` if search looks stale.
* `uv run companion-vault eval` prints retrieval quality (recall@k, MRR) on the fixture set;
  run it after changing chunking or ranking.
* Deleting a record removes it from the live database at once; backups made before the
  deletion still contain it until they rotate (default retention: 14 daily sets).

## Export and deletion
* `GET /v1/memory/export` (owner/desk) streams every record as JSON lines.
* `DELETE /v1/memory/documents/{id}` removes text and index entries and keeps a tombstone
  (title, hash, timestamps) for audit. `companion-vault stats` shows tombstone counts.

## Email (Gmail, read-only)
1. In Google Cloud Console create a project, enable the **Gmail API**, configure the OAuth
   consent screen as *External* with yourself as a **test user** (the `gmail.readonly` scope is
   a *restricted* scope; an unverified app is fine for its own test users, up to 100), and
   create an OAuth client of type **Desktop app**. Copy its client id and secret into `.env`
   as `COMPANION_GMAIL_CLIENT_ID` / `COMPANION_GMAIL_CLIENT_SECRET`.
2. Set `COMPANION_TOKEN_KEY` to a long random string (`openssl rand -base64 32`) and
   `email.provider: gmail` in `config/local.yaml`.
3. On the brain host run `uv run companion-api email-login`. It opens the consent page
   (or prints the address), receives the code on `127.0.0.1`, exchanges it with PKCE and
   stores the tokens encrypted in `data/secrets/email_tokens.enc` (mode 600).
4. `GET /v1/email/status` should report "Gmail connected as … (read-only)". The scope never
   allows sending, deleting or labelling.
5. To disconnect: `uv run companion-api email-logout` (revokes at Google and deletes the file),
   and/or remove the app at https://myaccount.google.com/permissions.
Order sync only runs when you ask ("what did I buy…", the Tools page button); bulk ingestion
is off unless `email.allow_bulk_ingest` is turned on.

## Weather, maths and card data
* Weather: set `weather.provider: open_meteo`, `latitude`, `longitude`, `location_name`. The
  forecast is cached in `data/cache/weather.json` for `cache_ttl_s`; when a refresh fails the
  cached one is shown and marked stale. Attribution to Open-Meteo is shown in the UI (CC BY 4.0).
* Maths needs nothing; it is SymPy with an allowlisted parser.
* Cards: `mtg.provider: scryfall` uses `https://api.scryfall.com` with the configured
  `user_agent`, paced requests and a 24-hour cache in `data/cache/scryfall/`. Scryfall asks
  consumers to cache and to keep under 10 requests per second; both are built in.

## Updates and rollback
`deploy/scripts/update.sh` (backup → fetch → stop → `uv sync --frozen` → UI build → migrate →
start) and `deploy/scripts/update.sh --rollback <ref>`. Migrations are forward-only; if one
ran, restore the pre-update backup set after rolling the code back.

## Troubleshooting
| Symptom | Check |
|---|---|
| UI says "Cannot reach the companion API" | `systemctl status companion-api`; `journalctl -u companion-api -n 50`; firewall between desk and brain |
| "model offline" badge | `curl http://<brain>:11434/api/version`; `ollama list`; `/readyz` detail says if the model lacks the `tools` capability |
| Lights do nothing, UI shows fixture badge | `home.provider` is still `fixture`; set `home_assistant`, token and `allowed_entities` |
| Transcription stuck in queued | worker not running (`systemctl status companion-worker`) or `stt.provider` disabled/fixture; `companion-worker list` |
| Reminder never fired | `companion-worker` must be running (it ticks the scheduler); check the schedule's `next_run_at` in `GET /v1/schedules` |
| Voice client: `arecord` not found / wrong device | `sudo apt install alsa-utils`; `arecord -l`; pass `--input-device plughw:X,Y` |
| Gmail 403 | account is not a test user of the OAuth client, or scope mismatch; re-run `companion-api email-login` |
| Disk full on the brain | recordings under `data/brain/media`; delete finished meetings from the Jobs page; `du -sh data/*` |
