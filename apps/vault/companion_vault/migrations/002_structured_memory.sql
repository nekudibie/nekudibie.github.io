-- Vault schema v2: structured memory. Every row carries provenance (an evidence document /
-- chunk / message id), a status that separates confirmed facts from inferred candidates,
-- and supersession links so history is retained while the current record is unambiguous.

CREATE TABLE facts (
    id                   TEXT PRIMARY KEY,
    subject              TEXT NOT NULL,              -- e.g. "owner", "desk lamp", "rover"
    predicate            TEXT NOT NULL,              -- e.g. "favourite tea", "timezone"
    value                TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'candidate',   -- candidate | confirmed | retracted | superseded | rejected
    confidence           REAL NOT NULL DEFAULT 0.5,
    scope                TEXT NOT NULL DEFAULT 'owner',
    stated_by            TEXT NOT NULL DEFAULT '',   -- client id or 'extractor'
    trust                TEXT NOT NULL DEFAULT 'inferred',  -- owner_stated | imported | inferred
    evidence_document_id TEXT REFERENCES documents(id),
    evidence_chunk_id    TEXT,
    evidence_message_id  TEXT,
    evidence_quote       TEXT,
    valid_from           TEXT,
    valid_to             TEXT,
    supersedes_id        TEXT REFERENCES facts(id),
    superseded_by_id     TEXT REFERENCES facts(id),
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    confirmed_at         TEXT,
    retracted_at         TEXT,
    note                 TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_facts_subject_pred ON facts(subject, predicate, status);
CREATE INDEX idx_facts_status ON facts(status, created_at DESC);

CREATE VIRTUAL TABLE facts_fts USING fts5(subject, predicate, value, content='facts', content_rowid='rowid', tokenize='porter unicode61 remove_diacritics 2');
CREATE TRIGGER facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, subject, predicate, value) VALUES (new.rowid, new.subject, new.predicate, new.value);
END;
CREATE TRIGGER facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, subject, predicate, value) VALUES ('delete', old.rowid, old.subject, old.predicate, old.value);
END;
CREATE TRIGGER facts_au AFTER UPDATE OF subject, predicate, value ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, subject, predicate, value) VALUES ('delete', old.rowid, old.subject, old.predicate, old.value);
    INSERT INTO facts_fts(rowid, subject, predicate, value) VALUES (new.rowid, new.subject, new.predicate, new.value);
END;

CREATE TABLE projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    name_key    TEXT NOT NULL UNIQUE,                -- lower-cased, trimmed
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active',      -- active | paused | done | archived
    scope       TEXT NOT NULL DEFAULT 'owner',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE decisions (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT REFERENCES projects(id),
    statement           TEXT NOT NULL,
    rationale           TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'current',  -- current | superseded | reversed
    scope               TEXT NOT NULL DEFAULT 'owner',
    decided_at          TEXT NOT NULL,
    stated_by           TEXT NOT NULL DEFAULT '',
    source_document_id  TEXT REFERENCES documents(id),
    source_chunk_id     TEXT,
    supersedes_id       TEXT REFERENCES decisions(id),
    superseded_by_id    TEXT REFERENCES decisions(id),
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX idx_decisions_project ON decisions(project_id, status, decided_at DESC);

CREATE TABLE actions (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    owner               TEXT,                        -- NULL = unknown, never invented
    owner_confidence    REAL NOT NULL DEFAULT 0,
    due_at              TEXT,                        -- ISO date/time when supported by evidence
    due_text            TEXT,                        -- the words actually used ("by Friday")
    due_confidence      REAL NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'draft',    -- draft | open | done | cancelled
    scope               TEXT NOT NULL DEFAULT 'owner',
    project_id          TEXT REFERENCES projects(id),
    meeting_id          TEXT,                        -- recording session id when from a meeting
    source_document_id  TEXT REFERENCES documents(id),
    source_chunk_id     TEXT,
    source_segment_id   TEXT,                        -- transcript segment
    source_quote        TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    completed_at        TEXT
);
CREATE INDEX idx_actions_status ON actions(status, due_at);
CREATE INDEX idx_actions_meeting ON actions(meeting_id);

CREATE TABLE purchases (
    id                  TEXT PRIMARY KEY,
    merchant            TEXT NOT NULL,
    merchant_key        TEXT NOT NULL,
    order_ref           TEXT NOT NULL,
    items_json          TEXT NOT NULL DEFAULT '[]',
    amount              REAL,
    currency            TEXT,
    ordered_at          TEXT,
    status              TEXT NOT NULL DEFAULT 'confirmed',  -- confirmed | shipped | delivered | cancelled | refunded
    status_history_json TEXT NOT NULL DEFAULT '[]',
    scope               TEXT NOT NULL DEFAULT 'owner',
    source_message_ids  TEXT NOT NULL DEFAULT '[]',
    source_document_id  TEXT REFERENCES documents(id),
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE(merchant_key, order_ref)
);

CREATE TABLE lesson_progress (
    id              TEXT PRIMARY KEY,
    course_id       TEXT NOT NULL,
    lesson_id       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'not_started',  -- not_started | in_progress | needs_review | mastered
    attempts        INTEGER NOT NULL DEFAULT 0,
    correct         INTEGER NOT NULL DEFAULT 0,
    last_score      REAL,
    weak_topics_json TEXT NOT NULL DEFAULT '[]',
    evidence_json   TEXT NOT NULL DEFAULT '[]',          -- list of {attempt_id, exercise_id, passed, at}
    scope           TEXT NOT NULL DEFAULT 'owner',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(course_id, lesson_id)
);
