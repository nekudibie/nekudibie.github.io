# Status

Last updated: 2026-10-03 (session 1). Legend: **tested locally** = automated tests pass in
the development container (x86_64, Python 3.12); **hardware-tested** = run on the real
device; **simulated** = fixture/simulator stands in for a real system and is labelled as
such; **blocked** = waiting on something outside the code; **unimplemented** = not started.

## Verification summary (this session)
* 185 automated tests pass (Python 3.11, 3.12 and 3.13 verified for the 181-test baseline;
  the four added on 2026-10-04 ran on 3.12); `ruff check` and `mypy` clean; desk UI builds
  with `tsc` + Vite.
* `./deploy/scripts/dev.sh` was run from a clean checkout: it installed the workspace, created
  `.env` and `config/local.yaml`, served the UI at `/`, answered `/v1/me` with the generated
  desk token, reported `/readyz` ready with vault/brain_db ok and every provider labelled
  fixture, and answered "turn on the desk lamp" deterministically with the fixture badge.
* **First run on Neku's own machine (2026-10-04, Ubuntu on WSL, Node 22):** `dev.sh` built
  the UI and started the API; the desk token connected; Gmail OAuth consent, encrypted token
  storage, status and search ran against the real Gmail API; **Sync from email** extracted
  real orders (Whatnot, Amazon and others). No model host or audio hardware yet, so no
  latency or benchmark figures exist. The branch is pushed to GitHub.
* Lessons from the first real inbox (all fixed and tested the same night): a 403 from Gmail
  turned out to be the Gmail API not being enabled in the Cloud project (the error now quotes
  Google's reason); merchant names from `*.co.uk` senders came out as "Co"; "Returns &
  Refunds" footer text marked orders as refunded; and purchases synced earlier from the
  fixture mailbox sat unlabelled beside real ones (now badged and removable, migration 003).

## Milestone summary

| # | Milestone | State |
|---|---|---|
| 0 | Audit, foundations, decisions | done |
| 1 | Runnable vertical slice | done, tested locally (66 tests), Ollama connectivity **blocked** (no model host in this container) |
| 2 | Home (HA adapter, allowlist, scenes, camera contract) | done against a fake HA server (tested locally); **not yet run against Neku's real Home Assistant** |
| 3 | Memory (structured memory, retrieval evaluation, backups) | done, tested locally (retrieval evaluation and restore test included) |
| 4 | Voice | software done and tested with fixtures; real STT/TTS adapters import-checked only; **hardware and model validation pending** |
| 5 | Meetings | done, tested locally with fixture STT (persistent jobs, resumable transcription, consent-gated recording, draft actions with uncertainty) |
| 6 | Tutor/reminders | done, tested locally (static exercise checks; schedules only on explicit acceptance; DST tests) |
| 7 | Personal tools | done with fixtures and mock servers; **Gmail live-tested on Neku's machine on 2026-10-04** (consent, status, search); **Open-Meteo and Scryfall not yet exercised live** (egress blocked here) |
| 8 | Deployment/reliability | assets done and syntax/consistency-tested; **not yet run on a real host** (no systemd/Docker daemon in this container) |
| 9 | Embodiment foundation | done, simulated and tested (bounded commands, watchdog, link-loss, bumper/cliff, e-stop, role denial) |

## What works now (tested locally)

* **Auth and permissions.** Bearer tokens → roles (`owner`, `desk`, `carried`, `rover`,
  `guest`, `service`) with server-side permission sets and per-client entity allowlists and
  memory scopes. Unauthenticated/invalid tokens get 401; wrong role gets 403; another client's
  conversation is inaccessible. (`tests/integration/test_auth_and_permissions.py`)
* **Tool gateway.** Unknown tools, schema-invalid arguments (extra fields, bad enums, non-JSON
  strings), unpermitted tools and non-allowlisted entities are refused before execution, with
  an audit row per attempt. A model "obeying" injected text in a note cannot actuate anything
  the client is not allowed to. (`test_gateway_and_injection.py`)
* **Conversation streaming.** SSE events `state/token/tool_call/tool_result/ui/sources/done/error`;
  partial output is persisted on cancel or disconnect; `/cancel` and the spoken "stop" interrupt
  an in-flight turn. (`test_cancellation.py`)
* **Deterministic routing** for stop/mute/time/"turn on X"/"dim X to N%"/"set <scene>"/
  "show <camera>", with honest replies for unknown or ambiguous names; works with the model
  down. (`test_router.py`, `test_gateway_and_injection.py::test_model_unavailable_*`)
* **Memory vault.** Notes/documents with provenance, offset anchors, FTS5 search with snippets,
  cited answers, honest empty results, corrections as revisions (only current found; history
  kept), deletion that removes index entries now and leaves a tombstone, idempotent import,
  export, reindex, embedded and remote modes. (`tests/unit/test_vault.py`,
  `test_memory_and_conversation.py`, `test_remote_vault.py`)
* **Ollama adapter.** Verified against the documented NDJSON shape with a mock server:
  streaming content and tool calls, `tool_name` tool messages, typed errors for missing
  model / unreachable host / timeout, health that reports the model's `tools` capability.
  (`test_ollama_adapter.py`) **Not yet exercised against a live Ollama.**
* **Desk UI.** React/TypeScript, builds cleanly (`npm run build`): clock, chat with streaming
  and tool chips, sources drawer that opens the cited record, notes (save/search/correct/
  delete/history), home panel (lights, brightness, scenes), camera panel with snapshot
  refresh and fixture labelling, transcript, settings with token and dependency status,
  offline/model-offline banners, state chip. Push-to-talk button present but disabled with
  an explanation (voice is Milestone 4). **Verified by TypeScript build and manual review of
  the API it calls; no browser automation test yet.**
* **Config and ops basics.** Validated YAML config, `.env` secrets, redacted JSON logs with
  request ids, migrations, `/healthz`, `/readyz`, `/version`, `check-config`, `make-token`,
  one-command `dev.sh`.

* **Home Assistant adapter.** REST calls match the documented endpoints (`/api/states`,
  `/api/services/<domain>/<service>`, `/api/camera_proxy[_stream]/<id>`), capabilities are
  derived from real attributes (`supported_color_modes`, `supported_features`), an explicit
  entity allowlist is enforced for the UI, the router and the model path, snapshots and MJPEG
  streams are proxied with server-side credentials and short-lived stream tickets, and an
  admin-only discovery view lists every entity with its allowed flag.
  (`tests/integration/test_home_assistant.py`, fake server in `tests/fixtures/`)

* **Structured memory.** Facts with `candidate` / `confirmed` / `superseded` / `retracted` /
  `rejected` statuses, provenance and validity windows; projects and decisions with
  supersession; actions that keep owner/deadline uncertainty; purchases with de-duplication
  and non-regressing status transitions; lesson progress from attempts. Conversation text is
  mined for *candidates* only (regex heuristics); the Notes page lists them for confirm/reject,
  and answers never use unconfirmed candidates. Works identically in embedded and remote
  vault modes. (`tests/unit/test_structured_memory.py`, `tests/integration/test_structured_api.py`)
* **Retrieval evaluation** (`companion-vault eval`, fixture set of 25 records / 35 queries):
  recall@1 = recall@5 = 0.914, MRR = 0.914. The three misses are deliberate paraphrases with
  no keyword overlap ("what hot drink do I like", "annual vehicle inspection", "my cycling
  security"). That is the current evidence base for deciding on local embeddings: keyword
  search handles direct recall well and fails on vocabulary mismatch, as expected.
* **Backup and restore.** Consistent online backups (SQLite backup API) with manifests and
  SHA-256 digests, pruning, verification before restore, live files moved aside not deleted;
  restore from a separate directory is tested. (`tests/unit/test_backup_and_eval.py`)

* **Voice path.** `POST /v1/audio/transcribe`, `POST /v1/audio/speak`, and
  `POST /v1/conversations/{id}/voice` (WAV in, SSE out with a `transcript` event, then the
  normal turn). Native client `companion-audio` with ALSA backends, push-to-talk, half-duplex
  echo avoidance, barge-in (press stops playback), software mute labelled as such, offline
  handling, optional wake-word loop with an in-memory ring buffer, `--simulate file.wav`.
  Tested in-process against the API with fixture STT/TTS (`tests/integration/test_audio_api.py`,
  `test_audio_client.py`). The faster-whisper and Piper adapters follow their documented
  APIs and import correctly on x86_64, but **no real recognition or synthesis has run here**:
  model downloads from Hugging Face are blocked in this container.

* **Persistent jobs.** `brain.db` job queue with atomic leased claims, lease expiry
  reclaim (crash recovery), idempotent enqueue keys, exponential retry, cancellation seen
  at the next heartbeat, a reserved slot for interactive work, audit events; embedded in
  the API for development or run as `companion-worker`. (`tests/unit/test_jobs.py`)
* **Meetings.** Recording starts only with an explicit consent flag (UI checkbox or desk
  client flag); the model's `meeting_start` tool is confirmation-gated and never executes
  from a model turn; "start recording" by voice opens the consent step. Audio arrives as
  checksummed WAV chunks written atomically (out-of-order and corrupted chunks rejected);
  pause/resume/stop/cancel; transcription resumes from a per-recording checkpoint after an
  interruption without duplicating segments; transcript (with time anchors), summary,
  decisions and draft actions are separate artefacts; owners and deadlines are only set when
  the words support them ("soon" keeps the text, no date); ambiguous meeting names are
  reported with dates rather than guessed; drafts become real actions only when confirmed on
  screen. Desk client: `companion-audio --record-meeting "Title" --participants-informed`.
  (`tests/integration/test_meetings.py`). **Fixture STT only here; the real pipeline
  (faster-whisper on the brain) is untested until a model host exists.**

* **Scheduler and reminders.** Persistent schedules in Europe/London; occurrences resolved
  with zoneinfo so 19:30 stays 19:30 across the March and October clock changes (tested on
  2026-03-29 and 2026-10-25); one alarm per occurrence however often the worker ticks; after
  downtime only the latest missed occurrence fires within the grace window and older ones
  are marked missed (no alarm storm); snooze/acknowledge; pause/resume/cancel/reschedule.
  Delivery is a server row the desk UI banner and the audio client poll; no model involved.
  (`tests/unit/test_scheduler.py`, `tests/integration/test_tutor_and_reminders.py`)
* **Python tutor.** Eight curated lessons referencing the official tutorial; every example's
  output is executed and verified by the test suite. Exercises are checked *statically*
  (AST requirements, forbidden constructs, user-reported output) and labelled as such;
  hints are revealed one per failed attempt; progress comes only from attempts
  (`in_progress` → `needs_review` → `mastered`), and the next lesson is chosen from it
  (review first, with a focus note on weak topics). Course plans are proposed as data and a
  lesson schedule exists only after the user accepts one; accepting again replaces it.
  Chat: "teach me Python" proposes, never schedules. **No code execution sandbox exists;**
  the Learn page says so. (`tests/unit/test_tutor.py`)
* **Weather.** Open-Meteo adapter (verified against the documented request/response shape
  with a mock server): disk cache with fetch time, stale labelling when a refresh fails,
  CC BY attribution shown; fixture provider labelled "invented numbers".
* **Maths.** SymPy behind an allowlist tokeniser (no builtins, no attribute access, exponent
  cap); solve/simplify/differentiate/integrate/evaluate with exact and approximate results;
  every answer says it was computed, not guessed. Injection attempts are rejected before
  parsing (tests cover `__import__`, `open`, attribute access, huge powers).
* **Magic decks.** Decklists saved as vault documents (sections, set codes, custom cards
  kept apart); legality from the card provider's `legalities` plus Comprehensive Rules
  100.2a / 903.5a-c quoted with each finding; colour identity, singleton/four-copy and deck
  size checks; ambiguous names are asked about, fuzzy matches offered not substituted;
  synergy is explicitly left as opinion. Scryfall adapter honours its headers, pacing and
  24 h cache rules (mock-tested).
* **Email and orders.** Read-only provider protocol; Gmail adapter (gmail.readonly scope,
  PKCE loopback consent via `companion-api email-login`, Fernet-encrypted token file,
  refresh on expiry, paging, bounded retries on 429/5xx, 403 guidance) tested with a mock
  Google; fixture mailbox with an injection email. Order extraction (merchant, reference,
  items, amount, status) with payment-detail redaction; sync de-duplicates by message id and
  never regresses a status (confirmation → dispatch → delivered; refund/cancel terminal).
  "What did I buy on Amazon" answers from stored purchases and says a confirmation is not
  proof of delivery.

* **Deployment assets.** `check-host.sh` (arch/OS/Python/RAM/disk/GPU/audio report),
  `setup-role.sh brain|vault|desk` (role-only `uv sync --frozen`, config/.env from examples,
  kiosk autostart on the desk), hardened systemd units with the worker at lower CPU/IO
  priority and a nightly backup timer, `update.sh` with backup-first and `--rollback`,
  `healthcheck.sh`, Dockerfile with locked dependencies, compose files for Ollama (one
  model, one parallel request), containerised API/worker/vault and Home Assistant, Caddy
  internal-CA example for HTTPS on the LAN. Verified here by `bash -n`, YAML parsing and
  unit content checks only (`tests/unit/test_deploy_assets.py`).
* **Embodiment (simulation).** `/v1/robot/*` with bounded `MotionCommand`s (rejected, not
  clamped, when outside the configured limits), server-side watchdog on every worker tick and
  request, link-loss/bumper/cliff stops, latched e-stop needing reset, stop available to any
  client that can see the robot, sensor injection admin-only. The `robot_command` tool lets
  a model request only high-level actions at a fixed fraction of the limits. Rover role
  cannot touch memory writes, home or cameras. (`tests/unit/test_robotics_sim.py`,
  `tests/integration/test_robot_api.py`) **No motor output exists anywhere in the code.**

## Simulated (always labelled as fixtures)
* Language model (`llm.provider: fixture`): pattern-based demo replies that still go through
  the real tool gateway.
* Home (`home.provider: fixture`): desk lamp, study ceiling, monitor plug, two scenes, one
  camera (SVG placeholder), one sensor.

## Blocked (outside the code)
* Live Ollama/model performance: no model host reachable from the development container.
  Benchmarks will be recorded only when run on Neku's brain host.
* Live Home Assistant, Hue/Govee/Tuya coverage and camera protocol: device inventory not yet
  supplied.
* Audio hardware validation (echo, interruption, latency) and real STT/TTS model runs: no
  microphone/speaker here and model downloads are blocked from this container.
* Email: Gmail is connected on Neku's Ubuntu/WSL dev machine (2026-10-04): OAuth consent,
  encrypted token store, status and search ran against the real API. The first attempt gave
  a 403 because the Gmail API was not enabled in the Cloud project; the adapter now quotes
  Google's reason. Order sync against Neku's real inbox is still being checked. Live
  Open-Meteo/Scryfall calls were impossible from this container and remain to be smoke-tested.
* Several vendor documentation sites were blocked by the container's egress proxy; GitHub
  mirrors were used (see docs/SOURCES.md). Re-check flagged items on a normal connection.

## Known gaps / next actions
1. Run the deployment on Neku's real hosts (brain first) and record measured model/STT
   latency and resource use in this file.
2. Token revocation without restart; rate limiting.
3. Browser-level UI test (Playwright) for the chat flow.
4. HLS/WebRTC camera streams (HA `camera/stream` WebSocket command) when a real camera exists.
5. Speaker diarisation as a separate optional job (none runs today; speakers are never invented).
6. LLM-assisted meeting summaries are wired (JSON with verbatim-quote checks) but only the
   rule-based extractor has run here, because no model host is reachable.

## Answers from Neku (2026-10-03)
1. GitHub access granted; the branch is pushed.
2. Email: Gmail, read-only. Neku created the Desktop OAuth client themselves (it needs
   their Google account) and on 2026-10-04 ran `dev.sh` and `email-login` on Ubuntu/WSL;
   the Tools tab shows "Gmail connected (read-only)". The client secret was pasted into chat
   during setup, so it should be reset in the Cloud Console and only ever live in `.env`.
3. Lights: three Govee lights, models not yet read; no Hue Bridge or camera details yet.
4. Hosts: the old machines were salvaged for parts and may not boot, so there is no confirmed
   brain host. Plan in docs/HARDWARE.md ("Brain").

## Still open
* Govee model numbers (H6xxx on each light), camera brand/model, whether any rescued board
  POSTs. The ordered plan for Neku's next session, including the bench test and the brain
  decision table, is docs/NEXT_STEPS.md.
* The order extractor has only been tuned on one real inbox; expect more shop-specific
  patterns to be needed. Statuses shown for real orders have not been checked against the
  actual emails by a person yet.
