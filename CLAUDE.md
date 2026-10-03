# Working in this repository

This is Neku's local-first desk companion monorepo. It also still hosts the GitHub
Pages files `index.html` and `privacy.html` (the *homecam* privacy policy). Leave
those two files alone unless Neku asks.

## Ground rules
- UK spelling in docs, UI copy and comments. Plain explanations for physical steps.
- Local-first: no cloud LLM or cloud audio path exists, and none may be added as a
  silent fallback. External integrations (weather, Scryfall, Gmail) are explicit,
  feature-flagged and documented in `docs/SOURCES.md`.
- Never write real credentials anywhere in the repo. Config refers to env vars.
- Fixtures must be labelled as fixtures end to end (`provider: "fixture"` on API
  responses, badges in the UI). Never present a fixture as live hardware.
- Tool execution is authorised in the gateway (`apps/api/companion_api/tools/gateway.py`)
  from the client's role; the model cannot widen permissions. Imported content is
  untrusted data and is wrapped as such before it reaches the model.
- Distinguish in `docs/STATUS.md`: locally tested, hardware-tested, simulated, blocked,
  unimplemented. Do not claim benchmarks that were not measured.

## Layout
- `packages/core` shared infra (config, logging, SQLite, auth), `packages/contracts` schemas,
  `packages/integrations` adapters, `packages/tutor`, `packages/robotics`.
- `apps/api` orchestration + tool gateway + serves the desk UI; `apps/vault` memory service;
  `apps/worker` jobs/schedules; `apps/audio` native audio client; `apps/desk` React UI.
- SQL migrations live next to the service that owns the database
  (`apps/vault/companion_vault/migrations`, `apps/api/companion_api/migrations`).

## Commands
- `uv sync` installs every role for development (one lockfile: `uv.lock`).
- `./deploy/scripts/dev.sh` one-command local start (creates `.env` tokens if missing).
- `uv run pytest` runs unit + fixture-backed integration tests; `uv run ruff check .`.
- `cd apps/desk && npm ci && npm run build` builds the UI the API serves.

## Decisions
Durable decisions are ADRs in `docs/decisions/`. Add one when you change an
architectural choice; update `docs/STATUS.md` at the end of every work session.
