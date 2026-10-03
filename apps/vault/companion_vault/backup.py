"""Consistent SQLite backups with manifests, pruning and verified restore.

* ``make_backup`` uses SQLite's online backup API (safe with WAL and live writers) for each
  database, copies the files directory, writes ``manifest.json`` with SHA-256 digests and
  prunes old sets beyond ``keep``.
* ``restore_backup`` verifies digests and ``PRAGMA quick_check`` on the copy *before* touching
  the live files, then moves the live files aside (``*.pre-restore-<ts>``) and swaps in the
  copies. It never deletes anything.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from companion_core.db import Database
from companion_core.errors import ValidationFailed
from companion_core.version import __version__


@dataclass
class BackupTarget:
    name: str  # e.g. "vault" or "brain"
    db_path: Path
    files_dir: Path | None = None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def make_backup(targets: list[BackupTarget], dest_root: Path, *, keep: int = 14) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = dest_root / stamp
    out.mkdir(parents=True, exist_ok=False)
    manifest: dict = {"created_at": stamp, "version": __version__, "entries": []}
    for t in targets:
        if not t.db_path.exists():
            manifest["entries"].append({"name": t.name, "db": None, "note": "database did not exist"})
            continue
        db_copy = out / f"{t.name}.db"
        Database(t.db_path).backup_to(db_copy)
        entry: dict[str, Any] = {"name": t.name, "db": db_copy.name, "sha256": _sha256(db_copy), "source": str(t.db_path), "schema": Database(db_copy).schema_version()}
        if t.files_dir and t.files_dir.is_dir():
            files_copy = out / f"{t.name}_files"
            shutil.copytree(t.files_dir, files_copy, dirs_exist_ok=True)
            entry["files"] = files_copy.name
            entry["files_count"] = sum(1 for _ in files_copy.rglob("*") if _.is_file())
        manifest["entries"].append(entry)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    prune(dest_root, keep=keep)
    return out


def list_backups(dest_root: Path) -> list[Path]:
    if not dest_root.is_dir():
        return []
    return sorted(p for p in dest_root.iterdir() if p.is_dir() and (p / "manifest.json").is_file())


def prune(dest_root: Path, *, keep: int) -> list[Path]:
    sets = list_backups(dest_root)
    removed = []
    for old in sets[: max(0, len(sets) - keep)]:
        shutil.rmtree(old)
        removed.append(old)
    return removed


def verify_backup(backup_dir: Path) -> dict:
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    for e in manifest["entries"]:
        if not e.get("db"):
            continue
        p = backup_dir / e["db"]
        if not p.is_file():
            raise ValidationFailed(f"backup is missing {e['db']}")
        if _sha256(p) != e["sha256"]:
            raise ValidationFailed(f"checksum mismatch for {e['db']}")
        with sqlite3.connect(str(p)) as conn:
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValidationFailed(f"{e['db']} failed quick_check")
    return manifest


def restore_backup(backup_dir: Path, targets: list[BackupTarget]) -> list[str]:
    manifest = verify_backup(backup_dir)
    by_name = {e["name"]: e for e in manifest["entries"]}
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    done: list[str] = []
    for t in targets:
        e = by_name.get(t.name)
        if not e or not e.get("db"):
            continue
        t.db_path.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            live = Path(str(t.db_path) + suffix)
            if live.exists():
                live.rename(Path(f"{t.db_path}{suffix}.pre-restore-{stamp}"))
        shutil.copy2(backup_dir / e["db"], t.db_path)
        if e.get("files") and t.files_dir is not None:
            if t.files_dir.exists():
                t.files_dir.rename(Path(f"{t.files_dir}.pre-restore-{stamp}"))
            shutil.copytree(backup_dir / e["files"], t.files_dir)
        done.append(t.name)
    return done
