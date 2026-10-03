-- Brain database v2: persistent jobs (with leases for crash recovery) and meeting recordings.

CREATE TABLE jobs (
    id               TEXT PRIMARY KEY,
    kind             TEXT NOT NULL,
    payload_json     TEXT NOT NULL DEFAULT '{}',
    idempotency_key  TEXT UNIQUE,
    priority         INTEGER NOT NULL DEFAULT 50,     -- lower runs sooner: 10 interactive, 50 background, 90 bulk
    status           TEXT NOT NULL DEFAULT 'queued',  -- queued | running | succeeded | failed | cancelled
    attempts         INTEGER NOT NULL DEFAULT 0,
    max_attempts     INTEGER NOT NULL DEFAULT 3,
    run_after        TEXT NOT NULL,
    leased_until     TEXT,
    worker_id        TEXT,
    heartbeat_at     TEXT,
    progress         REAL NOT NULL DEFAULT 0,
    progress_note    TEXT,
    result_json      TEXT,
    error            TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    client_id        TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    started_at       TEXT,
    finished_at      TEXT
);
CREATE INDEX idx_jobs_claim ON jobs(status, run_after, priority, created_at);
CREATE INDEX idx_jobs_client ON jobs(client_id, created_at DESC);

CREATE TABLE job_events (
    id      INTEGER PRIMARY KEY,
    job_id  TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    at      TEXT NOT NULL,
    kind    TEXT NOT NULL,     -- enqueued | claimed | progress | succeeded | failed | retry | cancelled | reclaimed
    note    TEXT
);
CREATE INDEX idx_job_events_job ON job_events(job_id, id);

CREATE TABLE recordings (
    id                     TEXT PRIMARY KEY,
    client_id              TEXT NOT NULL,
    title                  TEXT NOT NULL DEFAULT '',
    status                 TEXT NOT NULL DEFAULT 'recording',  -- recording | paused | stopped | processing | done | failed | cancelled
    participants_informed  INTEGER NOT NULL,
    route                  TEXT NOT NULL DEFAULT 'personal',   -- personal | employer_approved
    started_at             TEXT NOT NULL,
    paused_at              TEXT,
    paused_total_ms        INTEGER NOT NULL DEFAULT 0,
    stopped_at             TEXT,
    sample_rate            INTEGER NOT NULL DEFAULT 16000,
    channels               INTEGER NOT NULL DEFAULT 1,
    dir                    TEXT NOT NULL,
    chunk_count            INTEGER NOT NULL DEFAULT 0,
    bytes                  INTEGER NOT NULL DEFAULT 0,
    audio_ms               INTEGER NOT NULL DEFAULT 0,
    transcribed_through    INTEGER NOT NULL DEFAULT -1,        -- last chunk seq fully transcribed (resume point)
    transcript_document_id TEXT,
    summary_document_id    TEXT,
    error                  TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);
CREATE INDEX idx_recordings_client ON recordings(client_id, started_at DESC);

CREATE TABLE recording_chunks (
    recording_id  TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    seq           INTEGER NOT NULL,
    path          TEXT NOT NULL,
    bytes         INTEGER NOT NULL,
    sha256        TEXT NOT NULL,
    start_ms      INTEGER NOT NULL,   -- offset within the recording (pauses excluded)
    duration_ms   INTEGER NOT NULL,
    received_at   TEXT NOT NULL,
    PRIMARY KEY (recording_id, seq)
);

CREATE TABLE transcript_segments (
    id            TEXT PRIMARY KEY,
    recording_id  TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    chunk_seq     INTEGER NOT NULL,
    seq           INTEGER NOT NULL,
    start_ms      INTEGER NOT NULL,
    end_ms        INTEGER NOT NULL,
    text          TEXT NOT NULL,
    speaker       TEXT,              -- NULL unless a separate diarisation step filled it in
    confidence    REAL,
    created_at    TEXT NOT NULL,
    UNIQUE (recording_id, chunk_seq, seq)
);
CREATE INDEX idx_segments_recording ON transcript_segments(recording_id, start_ms);
