-- Brain database v1: conversations, messages and the tool-call audit trail.
-- Owned by the brain host (API + worker share it on local disk; never on SMB/NFS).

CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,
    client_id   TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    state       TEXT NOT NULL DEFAULT 'active',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX idx_conversations_client ON conversations(client_id, updated_at DESC);

CREATE TABLE messages (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL,
    content          TEXT NOT NULL,
    tool_name        TEXT,
    tool_calls_json  TEXT NOT NULL DEFAULT '[]',
    sources_json     TEXT NOT NULL DEFAULT '[]',
    meta_json        TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL
);
CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);

CREATE TABLE tool_invocations (
    id               INTEGER PRIMARY KEY,
    at               TEXT NOT NULL,
    conversation_id  TEXT,
    client_id        TEXT NOT NULL,
    call_id          TEXT NOT NULL,
    tool_name        TEXT NOT NULL,
    status           TEXT NOT NULL,          -- validated | invalid | denied | unknown_tool | ok | error
    reason           TEXT,
    args_json        TEXT NOT NULL DEFAULT '{}',
    duration_ms      INTEGER,
    route            TEXT NOT NULL DEFAULT 'llm'
);
CREATE INDEX idx_tool_invocations_conv ON tool_invocations(conversation_id, at);
