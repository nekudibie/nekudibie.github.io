-- Brain database v3: persistent schedules and reminder occurrences (no in-memory alarms).

CREATE TABLE schedules (
    id             TEXT PRIMARY KEY,
    client_id      TEXT NOT NULL,
    kind           TEXT NOT NULL,                 -- reminder | lesson | review
    title          TEXT NOT NULL,
    body           TEXT NOT NULL DEFAULT '',
    timezone       TEXT NOT NULL DEFAULT 'Europe/London',
    rule_json      TEXT NOT NULL,                 -- {"type":"once","at_local":"YYYY-MM-DDTHH:MM"} | {"type":"daily","time_local":"HH:MM"} | {"type":"weekly","days":[0..6],"time_local":"HH:MM"}
    next_run_at    TEXT,                          -- UTC instant of the next planned occurrence
    last_run_at    TEXT,
    status         TEXT NOT NULL DEFAULT 'active', -- active | paused | done | cancelled
    missed_policy  TEXT NOT NULL DEFAULT 'fire_late', -- fire_late | skip
    grace_minutes  INTEGER NOT NULL DEFAULT 120,
    payload_json   TEXT NOT NULL DEFAULT '{}',    -- e.g. {"course_id":..., "lesson_id":...}
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX idx_schedules_due ON schedules(status, next_run_at);
CREATE INDEX idx_schedules_client ON schedules(client_id, status);

CREATE TABLE reminders (
    id               TEXT PRIMARY KEY,
    schedule_id      TEXT NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    client_id        TEXT NOT NULL,
    due_at           TEXT NOT NULL,               -- planned occurrence (UTC)
    fired_at         TEXT,
    status           TEXT NOT NULL DEFAULT 'pending', -- pending | delivered | acknowledged | snoozed | missed | cancelled
    title            TEXT NOT NULL,
    body             TEXT NOT NULL DEFAULT '',
    kind             TEXT NOT NULL,
    payload_json     TEXT NOT NULL DEFAULT '{}',
    acknowledged_at  TEXT,
    snoozed_until    TEXT,
    delivery_count   INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    UNIQUE (schedule_id, due_at)                  -- one alarm per occurrence, however many times tick() runs
);
CREATE INDEX idx_reminders_client_status ON reminders(client_id, status, due_at);
