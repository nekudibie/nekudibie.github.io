"""SQLite helper: one writer at a time, WAL, foreign keys, numbered SQL migrations.

Each service owns exactly one database file on local disk (never SMB/NFS). Reads
use a per-thread connection; writes go through ``transaction()`` which takes a
process-wide lock so concurrent request threads serialise cleanly instead of
fighting over SQLite's own lock with busy-timeouts.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .logging import get_logger

log = get_logger(__name__)

_MIGRATION_RE = re.compile(r"^(\d{3,})_[a-z0-9_]+\.sql$")


def split_sql(script: str) -> list[str]:
    """Split a SQL script into complete statements (trigger bodies with inner ';' stay whole)."""
    statements: list[str] = []
    buf: list[str] = []
    for line in script.splitlines():
        stripped = line.strip()
        if not buf and (not stripped or stripped.startswith("--")):
            continue
        buf.append(line)
        candidate = "\n".join(buf)
        if sqlite3.complete_statement(candidate):
            statements.append(candidate.strip())
            buf = []
    tail = "\n".join(buf).strip()
    if tail and not all(ln.strip().startswith("--") or not ln.strip() for ln in tail.splitlines()):
        raise ValueError("migration script ends with an incomplete statement")
    return statements


class Database:
    def __init__(self, path: str | Path, *, busy_timeout_ms: int = 5000) -> None:
        self.path = Path(path)
        self.busy_timeout_ms = busy_timeout_ms
        self._local = threading.local()
        self._write_lock = threading.RLock()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn: sqlite3.Connection | None = None

    # -- connections -----------------------------------------------------
    def connect(self) -> sqlite3.Connection:
        if str(self.path) == ":memory:":
            # A single shared connection keeps in-memory databases usable across threads in tests.
            if self._memory_conn is None:
                self._memory_conn = self._open()
            return self._memory_conn
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._open()
            self._local.conn = conn
        return conn

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.path),
            timeout=self.busy_timeout_ms / 1000,
            isolation_level=None,  # we manage transactions explicitly
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {int(self.busy_timeout_ms)}")
        conn.execute("PRAGMA foreign_keys = ON")
        if str(self.path) != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
        if self._memory_conn is not None:
            self._memory_conn.close()
            self._memory_conn = None

    # -- transactions ----------------------------------------------------
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Serialised write transaction. Re-entrant within a thread."""
        with self._write_lock:
            conn = self.connect()
            nested = conn.in_transaction
            if not nested:
                conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                if not nested:
                    conn.execute("ROLLBACK")
                raise
            else:
                if not nested:
                    conn.execute("COMMIT")

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        return self.connect().execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        return self.connect().execute(sql, params).fetchone()

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self.transaction() as conn:
            return conn.execute(sql, params)

    # -- migrations ------------------------------------------------------
    def migrate(self, migrations_dir: Path) -> list[str]:
        """Apply every ``NNN_name.sql`` not yet recorded. Returns names applied."""
        files = sorted(p for p in migrations_dir.iterdir() if _MIGRATION_RE.match(p.name))
        applied: list[str] = []
        with self.transaction() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))"
            )
            done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations")}
            for path in files:
                if path.name in done:
                    continue
                # Note: sqlite3.executescript() would COMMIT the outer transaction first,
                # so scripts are split into statements and run with execute().
                conn.execute("SAVEPOINT mig")
                try:
                    for stmt in split_sql(path.read_text(encoding="utf-8")):
                        conn.execute(stmt)
                    conn.execute("INSERT INTO schema_migrations(name) VALUES (?)", (path.name,))
                    conn.execute("RELEASE mig")
                except sqlite3.Error:
                    conn.execute("ROLLBACK TO mig")
                    conn.execute("RELEASE mig")
                    raise
                applied.append(path.name)
        if applied:
            log.info("migrations applied", extra={"db": str(self.path), "applied": applied})
        return applied

    def schema_version(self) -> str | None:
        try:
            row = self.query_one("SELECT name FROM schema_migrations ORDER BY name DESC LIMIT 1")
        except sqlite3.OperationalError:
            return None
        return row["name"] if row else None

    def integrity_ok(self) -> bool:
        row = self.query_one("PRAGMA quick_check")
        return row is not None and row[0] == "ok"

    def backup_to(self, dest: str | Path) -> Path:
        """Consistent online backup using SQLite's backup API (safe while WAL is active)."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = self.connect()
        with sqlite3.connect(str(dest)) as out:
            src.backup(out)
        return dest
