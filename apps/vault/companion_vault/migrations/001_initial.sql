-- Vault schema v1: documents (authoritative originals), chunks (derived, rebuildable),
-- FTS5 index (derived), audit log. Structured memory tables arrive in 002.

CREATE TABLE documents (
    id               TEXT PRIMARY KEY,
    kind             TEXT NOT NULL,
    title            TEXT NOT NULL DEFAULT '',
    text             TEXT,                      -- authoritative original for text records (NULL after deletion)
    mime_type        TEXT NOT NULL DEFAULT 'text/plain',
    scope            TEXT NOT NULL DEFAULT 'owner',
    project          TEXT,
    source_type      TEXT NOT NULL,
    source_ref       TEXT NOT NULL DEFAULT '',
    source_uri       TEXT,
    captured_by      TEXT NOT NULL DEFAULT '',
    captured_at      TEXT,
    trust            TEXT NOT NULL DEFAULT 'imported',
    content_sha256   TEXT NOT NULL,
    revision         INTEGER NOT NULL DEFAULT 1,
    supersedes_id    TEXT REFERENCES documents(id),
    superseded_by_id TEXT REFERENCES documents(id),
    idempotency_key  TEXT,
    metadata_json    TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    deleted_at       TEXT
);
CREATE INDEX idx_documents_kind_created ON documents(kind, created_at DESC);
CREATE INDEX idx_documents_project ON documents(project) WHERE project IS NOT NULL;
CREATE INDEX idx_documents_source ON documents(source_type, source_ref);
CREATE UNIQUE INDEX idx_documents_idem ON documents(idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE TABLE chunks (
    rid          INTEGER PRIMARY KEY,           -- stable integer rowid for the FTS external-content link
    id           TEXT NOT NULL UNIQUE,
    document_id  TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    seq          INTEGER NOT NULL,
    text         TEXT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    anchor_json  TEXT NOT NULL DEFAULT '{}',
    UNIQUE(document_id, seq)
);

CREATE VIRTUAL TABLE chunks_fts USING fts5(
    text, title,
    content='chunks', content_rowid='rid',
    tokenize='porter unicode61 remove_diacritics 2'
);

CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, title) VALUES (new.rid, new.text, new.title);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, title) VALUES ('delete', old.rid, old.text, old.title);
END;
CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, title) VALUES ('delete', old.rid, old.text, old.title);
    INSERT INTO chunks_fts(rowid, text, title) VALUES (new.rid, new.text, new.title);
END;

CREATE TABLE audit_log (
    id           INTEGER PRIMARY KEY,
    at           TEXT NOT NULL,
    actor        TEXT NOT NULL,
    action       TEXT NOT NULL,
    target_id    TEXT,
    details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_audit_target ON audit_log(target_id);
