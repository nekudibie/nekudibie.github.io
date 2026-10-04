# Neku's desk companion

A local-first personal assistant that lives on a desk: a screen, microphone and speakers in
front of you, a "brain" host running a local language model, and a memory vault that keeps
your notes, decisions, meetings and lesson progress with real citations. Nothing talks to a
cloud model; the few external integrations (weather, card data, read-only email) are explicit
and switchable.

This repository also still serves the GitHub Pages files `index.html` and `privacy.html`
(the *homecam* privacy policy); they are unrelated to the companion and left untouched.

## Shortest working start (one machine, no hardware)

Requirements: Linux or macOS, [uv](https://docs.astral.sh/uv/), Node 20+ (for the UI build).

```bash
./deploy/scripts/dev.sh
```

That installs the Python workspace, creates `.env` with fresh tokens, builds the desk UI and
starts the API on http://127.0.0.1:8710 with every provider in **fixture** mode (a scripted
demo model, a simulated home, a placeholder camera). Open the address, go to **Settings**,
paste the desk token the script printed, and try:

* "Turn on the desk lamp" → routed deterministically, answered with a *fixture* badge.
* "Remember that we decided to use SQLite FTS5 for the Lantern project" → saved to the vault.
* "What did we decide about the Lantern project?" → answer with a `[S1]` citation; open it.
* "What did I buy from Amazon?" → an honest "no record" rather than a guess.
* "Show the front door camera" → the camera panel opens, clearly labelled as a placeholder.

To use a real model, install [Ollama](https://ollama.com) on the brain host, pull a model that
reports the `tools` capability, and set `llm.provider: ollama` plus `llm.model` in
`config/local.yaml`. `GET /readyz` tells you whether the model is reachable and tool-capable.

## What it does today

Chat with citations from your own notes, facts and decisions; home control through Home
Assistant with an explicit allowlist; camera snapshots/streams; push-to-talk voice with a
native desk client; consent-gated meeting recording with resumable transcription, summaries
and draft actions; a Python tutor with verified examples and static exercise checks;
restart-safe Europe/London reminders; weather (Open-Meteo), exact maths (SymPy), Magic deck
legality with rule citations, and read-only Gmail search with order tracking. Everything
external is switchable and labelled; see `docs/STATUS.md` for what has and has not been
verified on real hardware.

## Commands

| Command | What it does |
|---|---|
| `make dev` / `./deploy/scripts/dev.sh` | one-command local start |
| `uv run pytest -q` | unit + fixture-backed integration tests |
| `uv run ruff check .` | lint |
| `uv run companion-api check-config` | validate `config/local.yaml` + `.env`, print a redacted summary |
| `uv run companion-api make-token` | generate a client token |
| `uv run companion-api serve` / `companion-vault serve` | run one role |
| `cd apps/desk && npm run build` | rebuild the desk UI the API serves |
| `deploy/scripts/check-host.sh` | is this machine fit for a role? (arch, Python, RAM, disk, GPU, audio) |
| `deploy/scripts/setup-role.sh brain\|vault\|desk` | install one role on a real host, then `install-units.sh <role> --enable` |
| `deploy/scripts/update.sh` / `--rollback <ref>` | backup-first update, rollback |

## Where things are

* `docs/NEXT_STEPS.md` the current step-by-step plan for Neku (software, identification, bench test, decisions).
* `docs/STATUS.md` what works, how it was verified, what is simulated, what is blocked.
* `docs/ARCHITECTURE.md` roles, request flow, trust boundaries, data ownership.
* `docs/BUILD_GUIDE.md` assembly and deployment stage by stage, with checkpoints.
* `docs/HARDWARE.md` inventory template and a conditional reuse/buy list.
* `docs/OPERATIONS.md` start/stop, health, logs, secure access, backup/restore, export/deletion.
* `docs/SECURITY.md` the permission model and what the language model cannot do.
* `docs/SOURCES.md` primary references with the date they were checked.
* `docs/decisions/` architecture decision records.

## Layout

```
apps/api       orchestration API, tool gateway, serves the desk UI     apps/desk    React/TypeScript desk UI
apps/vault     memory vault service and clients                        apps/audio   native audio client (Milestone 4)
apps/worker    persistent jobs and schedules (Milestones 5–6)          packages/*   core, contracts, integrations, tutor, robotics
deploy/        compose, systemd, scripts                               tests/       unit, integration, e2e, fixtures
```

## Licence

MIT for this repository's code. Third-party components keep their own licences (notably
Piper TTS is GPL-3.0 and runs as a separate optional component).
