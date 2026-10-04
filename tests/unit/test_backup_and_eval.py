from __future__ import annotations

from pathlib import Path

import pytest
from companion_contracts.vault import NoteCreate, SearchRequest
from companion_core.db import Database
from companion_core.errors import ValidationFailed
from companion_vault.backup import (
    BackupTarget,
    list_backups,
    make_backup,
    restore_backup,
    verify_backup,
)
from companion_vault.evaluation import default_fixture_dir, load_jsonl, run_evaluation
from companion_vault.service import VaultService


def _vault(path: Path) -> VaultService:
    s = VaultService(Database(path))
    s.migrate()
    return s


def test_backup_restore_from_separate_target(tmp_path: Path):
    live = tmp_path / "live" / "vault.db"
    files = tmp_path / "live" / "files"
    files.mkdir(parents=True)
    (files / "audio.txt").write_text("pretend recording")
    svc = _vault(live)
    svc.create_note(NoteCreate(text="The greenhouse heater is on a timer from 6 to 9."), actor="desk")
    dest = tmp_path / "elsewhere" / "backups"  # a separate target directory
    out = make_backup([BackupTarget("vault", live, files)], dest, keep=14)
    manifest = verify_backup(out)
    assert manifest["entries"][0]["schema"] == "003_purchase_provenance.sql" and manifest["entries"][0]["files_count"] == 1

    # damage the live database and the files directory, then restore
    svc.db.close()
    live.write_bytes(b"garbage" * 100)
    (files / "audio.txt").unlink()
    restored = restore_backup(out, [BackupTarget("vault", live, files)])
    assert restored == ["vault"]
    assert any(p.name.startswith("vault.db.pre-restore-") for p in live.parent.iterdir())
    svc2 = _vault(live)
    assert svc2.search(SearchRequest(query="greenhouse heater timer"), scopes=["owner"]).hits
    assert (files / "audio.txt").read_text() == "pretend recording"


def test_backup_pruning_and_corruption_detection(tmp_path: Path):
    live = tmp_path / "vault.db"
    _vault(live).create_note(NoteCreate(text="x"), actor="desk")
    dest = tmp_path / "bk"
    import time

    outs = []
    for _ in range(3):
        outs.append(make_backup([BackupTarget("vault", live)], dest, keep=2))
        time.sleep(1.1)  # folder names are second-resolution timestamps
    assert len(list_backups(dest)) == 2 and not outs[0].exists()
    (outs[-1] / "vault.db").write_bytes(b"corrupt")
    with pytest.raises(ValidationFailed, match="checksum"):
        verify_backup(outs[-1])
    with pytest.raises(ValidationFailed):
        restore_backup(outs[-1], [BackupTarget("vault", live)])
    assert Database(live).query_one("SELECT COUNT(*) FROM documents")[0] == 1  # live untouched


def test_retrieval_evaluation_meets_floor_and_reports_misses():
    d = default_fixture_dir()
    res = run_evaluation(load_jsonl(d / "corpus.jsonl"), load_jsonl(d / "queries.jsonl"))
    out = res.to_dict()
    # Keyword retrieval floor on the fixture set; paraphrase queries are expected to miss and are
    # the evidence for (or against) adding embeddings later.
    assert out["queries"] >= 30
    assert out["recall_at_5"] >= 0.85, out
    assert out["mrr"] >= 0.75, out
    assert all(m["query"].startswith("paraphrase:") for m in out["misses"]), out["misses"]
