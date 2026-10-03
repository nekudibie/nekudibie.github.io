# ADR 0006: Inferred memory is a candidate until the owner confirms it

**Status:** accepted (2026-10-03)

**Context.** The assistant should learn preferences and records from conversation, but
"perfect recall" and silent inference both erode trust: an inferred guess that is later
quoted as fact is worse than no memory.

**Decision.** `facts` rows carry a status: `candidate` (inferred by the extractor or a
model, confidence < 1, trust `inferred`), `confirmed` (explicitly stated or confirmed by the
owner), `superseded`, `retracted`, `rejected`. Retrieval and answers use confirmed facts
only; the UI lists candidates separately for confirm/reject. Confirming or stating a new
value for the same subject/predicate supersedes the old confirmed value and keeps it in
history with `valid_to`. Decisions follow the same pattern (`current` / `superseded` /
`reversed`). Every row names its evidence (document, chunk or message id plus a quote).

**Consequences.** Answers can always say whether something was stated or guessed and when
it changed. The extractor can stay simple and conservative (regex heuristics now, a model
job later) because it can never promote its own output.
