# ADR 0004: Deterministic routing for stop/mute and common home commands

**Status:** accepted (2026-10-03)

**Context.** "Stop", "mute", the time and "turn on the desk lamp" must work when the
model is down, slow or wrong.

**Decision.** `DeterministicRouter` matches a small set of patterns before any model call
and resolves device names against the client's allowlisted entities (config aliases,
scene names, friendly names, unique substrings). Ambiguity produces an honest reply
listing known devices rather than a guess. Open-ended requests go to the model.

**Consequences.** Basic control is independent of Ollama; the pattern set is documented
and tested; phrasing outside it still works via the model's `home_control` tool.
