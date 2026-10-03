# Architecture

Neku's companion is a local-first personal assistant split into three *roles*. The
roles are a deployment choice, not an application boundary: the same code runs as
one process on a laptop, as two hosts, or as three.

| Role  | Runs                                                                 | Owns on disk                              |
|-------|----------------------------------------------------------------------|-------------------------------------------|
| Desk  | kiosk browser showing the desk UI; `companion-audio` (native capture/playback) | nothing durable (ephemeral audio buffers) |
| Brain | `companion-api` (orchestration, tool gateway, serves the desk UI), `companion-worker` (jobs/schedules), Ollama, STT/TTS | `brain.db` (conversations, jobs, schedules, audit), meeting media |
| Vault | `companion-vault` (memory service), Home Assistant Container, backups | `vault.db` (documents, chunks, FTS index, structured memory), archived files |

## Code layout

```
packages/core          config, logging (JSON + redaction), SQLite helper + migrations, auth primitives, ids, clock
packages/contracts     Pydantic schemas: stream events, tool specs/args, vault, home, health
packages/integrations  adapters: llm (ollama, fixture, scripted), home (fixture, home_assistant), later weather/email/mtg/stt/tts
packages/tutor         lessons, exercises, progress (Milestone 6)
packages/robotics      embodiment contracts + simulator (Milestone 9)
apps/vault             VaultService (the only code touching vault.db), HTTP app, Local/Http clients
apps/api               FastAPI app: auth deps, conversation store, deterministic router, orchestrator, tool gateway, routes
apps/worker            persistent job runner (Milestone 5/6)
apps/audio             native Linux/Pi audio client (Milestone 4)
apps/desk              React/TypeScript desk UI (built to apps/desk/dist, served by the API)
```

## Request flow for a turn

```
desk UI ──POST /v1/conversations/{id}/messages (bearer token)──► companion-api
   ▲                                                                │ 1. authenticate client → ClientIdentity(role, permissions, allowlists)
   │ SSE: state / token / tool_call / tool_result / ui / sources /  │ 2. persist user message (brain.db)
   │      done / error                                              │ 3. DeterministicRouter: stop, mute, time, "turn on X", "set Y", "show Z camera"
   │                                                                │ 4. else LLM loop: system prompt + recent turns + permitted tool specs
   │                                                                │    ↳ Ollama /api/chat (stream) ─ tool_calls ─► ToolGateway
   │                                                                │ 5. ToolGateway: exists? enabled? permitted? schema-valid? allowlisted? → execute (timeout) → audit
   │                                                                │ 6. tool output wrapped as <<<untrusted ...>>> and fed back; sources relabelled S1..Sn
   └──────────────────────────────────────────────────────────────── 7. persist assistant message with sources + meta
```

The model never talks to Home Assistant, the vault or anything else directly. It can
only *propose* a tool call; the gateway decides. The same gateway serves the UI's
own buttons (route `ui`) and the deterministic router (route `deterministic`), so one
audit trail covers every actuation.

## Data ownership

* Each SQLite database has exactly one owning service on local disk, WAL mode, a
  process-wide write lock in the owning process. `brain.db` is shared by the API and
  worker *on the same host only*. Nothing is ever placed on SMB/NFS.
* Originals are authoritative; chunks and the FTS5 index are derived and rebuildable
  (`companion-vault reindex`).
* Corrections create a new revision linked by `supersedes_id`; retrieval returns only
  current revisions unless history is requested. Deletion removes chunks/index now and
  blanks the original, leaving a tombstone; backups rotate on their own schedule.

## Moving services between hosts

Only configuration changes:

* `vault.mode: embedded` → `remote` plus `vault.url` and a service token switches the
  API from `LocalVaultClient` to `HttpVaultClient`. The orchestrator and tools use the
  `VaultClient` protocol and are unchanged.
* `worker.embedded: true` runs jobs inside the API process (development);
  `false` means a separate `companion-worker` process on the brain host.
* `llm.base_url`, `home.base_url` point at wherever Ollama and Home Assistant live.

## Trust boundaries

* Clients authenticate with bearer tokens mapped to roles (`owner`, `desk`, `carried`,
  `rover`, `guest`, `service`). Roles are fixed server-side.
* Imported notes, emails, OCR and every tool result are untrusted data. They are wrapped
  before reaching the model, and nothing in them can widen permissions because the
  gateway checks the *client's* permissions, not the model's wishes.
* Camera and Home Assistant credentials never leave the API host; the UI fetches
  snapshots through the API with its own client token.

## Streaming contract

Events are Server-Sent Events, one JSON object per event, typed in
`packages/contracts/companion_contracts/events.py`. The UI drives its state machine
(`idle, listening, transcribing, thinking, tool_running, speaking, muted, recording,
offline, error`) from `state` events and local audio state; it never infers "speaking"
from text alone.

## Why these choices (short form; ADRs in docs/decisions)

* SQLite + FTS5 before any vector engine: keyword retrieval with citations is
  inspectable and fast on a Pi; embeddings come only when the retrieval evaluation
  (Milestone 3) shows a gain.
* uv workspace with one lockfile: role-specific installs (`uv sync --package companion-vault`)
  from a single reproducible resolution.
* A deterministic router in front of the model: stop, mute and common home commands keep
  working when the model host is down or slow.
