# ADR 0002: SQLite + FTS5 keyword retrieval before any vector engine

**Status:** accepted (2026-10-03)

**Context.** The vault must give cited, correctable answers on modest hardware, and
originals must stay authoritative.

**Decision.** Store originals in `documents`; derive `chunks` with offset anchors and an
FTS5 index (`porter unicode61`, bm25 with title weighting). Search tries an AND query,
then OR; results carry chunk ids and anchors so citations can be re-opened. Embeddings
and a vector index are added only if the retrieval evaluation (Milestone 3) shows a
measured gain.

**Consequences.** Simple operations and backups (one file, SQLite backup API); rebuildable
index; synonyms/paraphrase recall is weaker until embeddings are justified.
