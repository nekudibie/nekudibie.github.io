# ADR 0007: Persistent leased jobs; recording is explicit and consent-gated

**Status:** accepted (2026-10-03)

**Context.** Meeting transcription is long-running and must survive crashes; reminders must
fire without a model; recording other people needs an explicit, visible, consent-aware start.

**Decision.**
* Jobs live in `brain.db` (`jobs`, `job_events`). A worker claims a job atomically with a
  lease; expired leases are reclaimed so a crashed worker's job re-runs. Handlers are
  idempotent and checkpoint their own progress (transcription records
  `transcribed_through` per recording; segment inserts are unique per chunk/seq).
  Priority lanes keep one slot for interactive jobs (< 20) so bulk work cannot starve them.
  The runner is embedded in the API process in development and a separate
  `companion-worker` process on real hosts; same code, same database file, same host.
* A recording starts only through an explicit request carrying
  `participants_informed: true` (UI checkbox or desk client flag). The model's
  `meeting_start` tool is marked `requires_confirmation`, so the gateway never executes it
  from a model turn; the spoken "start recording" opens the Jobs page with the consent box.
  Stop/pause/resume are allowed by voice. The UI shows a persistent REC indicator from the
  server's own state, not from a client-side flag.
* Audio arrives as complete WAV chunks written atomically; transcript, audio, summary,
  decisions and draft actions are separate artefacts with provenance back to segments.
  Speakers are never inferred. Extracted actions stay `draft` until the user confirms them.

**Consequences.** No in-memory queues; restarts are safe; the consent step is a product
rule enforced in code, not a prompt instruction.
