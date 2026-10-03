# Status

Last updated: 2026-10-03 (session 1). Legend: **tested locally** = automated tests pass in
the development container (x86_64, Python 3.12); **hardware-tested** = run on the real
device; **simulated** = fixture/simulator stands in for a real system and is labelled as
such; **blocked** = waiting on something outside the code; **unimplemented** = not started.

## Milestone summary

| # | Milestone | State |
|---|---|---|
| 0 | Audit, foundations, decisions | done |
| 1 | Runnable vertical slice | done, tested locally (66 tests), Ollama connectivity **blocked** (no model host in this container) |
| 2 | Home (HA adapter, allowlist, scenes, camera contract) | done against a fake HA server (tested locally); **not yet run against Neku's real Home Assistant** |
| 3 | Memory (structured memory, retrieval evaluation, backups) | done, tested locally (retrieval evaluation and restore test included) |
| 4 | Voice | unimplemented (research done; see docs/SOURCES.md) |
| 5 | Meetings | unimplemented |
| 6 | Tutor/reminders | unimplemented |
| 7 | Personal tools (email, orders, weather, maths, MTG) | unimplemented |
| 8 | Deployment/reliability | partly: dev script, Makefile; compose/systemd/backup scripts unimplemented |
| 9 | Embodiment foundation | unimplemented |

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
* Audio hardware validation (echo, interruption, latency): no microphone/speaker.
* Email provider: awaiting confirmation (Gmail assumed as the likely first adapter).
* Several vendor documentation sites were blocked by the container's egress proxy; GitHub
  mirrors were used (see docs/SOURCES.md). Re-check flagged items on a normal connection.

## Known gaps / next actions
1. Milestone 4: native audio client, STT/TTS adapters, push-to-talk, cancellation, wake word.
2. Token revocation without restart; rate limiting.
3. Browser-level UI test (Playwright) for the chat flow.
4. HLS/WebRTC camera streams (HA `camera/stream` WebSocket command) when a real camera exists.

## Questions for Neku (answers unblock specific work; nothing else waits on them)
1. Email provider: is Gmail the first account to connect (read-only)? If so, are you willing
   to create a Google Cloud project with a *Desktop* OAuth client for your own use?
2. Hue: is there a Hue Bridge? Govee: model numbers? Camera: brand/model and whether it offers
   RTSP/ONVIF?
3. Which rescued machine boots? (motherboard model, CPU, RAM amount) — decides whether the
   brain is a rescued PC or needs a purchase.
