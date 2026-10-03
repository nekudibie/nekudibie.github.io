from __future__ import annotations

import pytest
from companion_contracts.common import Provenance
from companion_contracts.vault import CorrectionRequest, DocumentImport, NoteCreate, SearchRequest
from companion_core.db import Database
from companion_core.errors import Conflict, NotFound
from companion_vault.chunking import chunk_text
from companion_vault.fts import fts_query, keyword_terms
from companion_vault.service import VaultService


@pytest.fixture
def svc(tmp_path):
    s = VaultService(Database(tmp_path / "vault.db"), chunk_chars=300, chunk_overlap_chars=40)
    s.migrate()
    return s


def test_chunk_anchors_point_back_into_original():
    text = "\n\n".join(f"Paragraph {i}. " + ("word " * 40) for i in range(8))
    chunks = chunk_text(text, chunk_chars=400, overlap_chars=50)
    assert len(chunks) > 2
    for c in chunks:
        assert text[c.start:c.end].strip() == c.text
    assert [c.seq for c in chunks] == list(range(len(chunks)))


def test_long_paragraph_is_split_with_overlap():
    text = "sentence one. " * 200
    chunks = chunk_text(text, chunk_chars=300, overlap_chars=60)
    assert len(chunks) > 5
    assert all(len(c.text) <= 300 for c in chunks)
    assert chunks[1].start < chunks[0].end  # overlap


def test_fts_query_quotes_and_prefixes():
    terms = keyword_terms('What did we "decide" about the Lantern-project?')
    assert "decide" in terms and "lantern" in terms and "the" not in terms
    q = fts_query(["o'brien", "lan"], mode="AND")
    assert q == '"o\'brien" AND "lan"*'
    assert fts_query(['a"b'], prefix_last=False) == '"a""b"'


def test_search_cites_chunk_with_anchor_and_scope(svc):
    doc = svc.create_note(NoteCreate(text="Action from the Orion meeting: Neku to send the budget sheet by Friday."), actor="desk")
    res = svc.search(SearchRequest(query="orion budget action"), scopes=["owner"])
    assert res.hits and res.hits[0].document_id == doc.id
    h = res.hits[0]
    assert h.anchor.kind == "offset" and doc.text[h.anchor.start : h.anchor.end].strip() == h.text
    assert "budget" in h.snippet.lower()
    # a client limited to the shared scope cannot see owner notes
    assert svc.search(SearchRequest(query="orion budget", scopes=["shared"]), scopes=["shared"]).hits == []
    assert svc.search(SearchRequest(query="orion budget"), scopes=["shared"]).hits == []


def test_missing_evidence_is_empty_not_guess(svc):
    svc.create_note(NoteCreate(text="Bought a kettle from Argos in March."), actor="desk")
    res = svc.search(SearchRequest(query="unicorn delivery from amazon"), scopes=["owner"])
    assert res.hits == [] and res.strategy == "none"


def test_correction_keeps_history_and_only_current_is_found(svc):
    d1 = svc.create_note(NoteCreate(text="Decision: the rover uses a Pi 4 as its onboard computer."), actor="desk")
    d2 = svc.correct(d1.id, CorrectionRequest(new_text="Decision: the rover uses a Pi 5 as its onboard computer (changed from Pi 4).", reason="hardware changed"), actor="desk", scopes=["owner"])
    assert d2.revision == 2 and d2.supersedes_id == d1.id
    hits = svc.search(SearchRequest(query="rover onboard computer"), scopes=["owner"]).hits
    assert [h.document_id for h in hits] == [d2.id] and hits[0].is_current
    old = svc.get_document(d1.id, scopes=["owner"])
    assert old.superseded_by_id == d2.id
    assert [d.revision for d in svc.history(d1.id, scopes=["owner"])] == [1, 2]
    with pytest.raises(Conflict):
        svc.correct(d1.id, CorrectionRequest(new_text="again"), actor="desk", scopes=["owner"])
    hist = svc.search(SearchRequest(query="rover onboard computer", include_superseded=True), scopes=["owner"]).hits
    assert {h.document_id for h in hist} == {d1.id, d2.id}


def test_delete_removes_index_and_text_but_keeps_tombstone(svc):
    d = svc.create_note(NoteCreate(text="Temporary secret plan about the surprise party."), actor="desk")
    assert svc.search(SearchRequest(query="surprise party"), scopes=["owner"]).hits
    out = svc.delete(d.id, actor="desk", scopes=["owner"], reason="user asked")
    assert out.deleted and out.chunks_removed == 1 and "Backups" in out.note
    assert svc.search(SearchRequest(query="surprise party"), scopes=["owner"]).hits == []
    tomb = svc.get_document(d.id, scopes=["owner"])
    assert tomb.deleted_at and tomb.text is None
    assert svc.list_documents(scopes=["owner"]) == []
    with pytest.raises(Conflict):
        svc.correct(d.id, CorrectionRequest(new_text="x"), actor="desk", scopes=["owner"])


def test_import_is_idempotent_and_conflicts_on_changed_content(svc):
    prov = Provenance(source_type="email", source_ref="msg-1", source_uri="https://mail.example/msg-1")
    imp = DocumentImport(title="Order 123", text="Your order 123 has shipped.", kind="email", provenance=prov, idempotency_key="email:msg-1")
    a = svc.import_document(imp, actor="worker")
    b = svc.import_document(imp, actor="worker")
    assert a.id == b.id
    with pytest.raises(Conflict):
        svc.import_document(imp.model_copy(update={"text": "different"}), actor="worker")


def test_reindex_rebuilds_from_originals(svc):
    svc.create_note(NoteCreate(text="Alpha beta gamma."), actor="desk")
    svc.create_note(NoteCreate(text="Delta epsilon."), actor="desk")
    svc.db.execute("DELETE FROM chunks")
    assert svc.search(SearchRequest(query="gamma"), scopes=["owner"]).hits == []
    assert svc.rebuild_index() == 2
    assert svc.search(SearchRequest(query="gamma"), scopes=["owner"]).hits


def test_scope_hides_documents(svc):
    d = svc.create_note(NoteCreate(text="private thing", scope="private"), actor="desk")
    with pytest.raises(NotFound):
        svc.get_document(d.id, scopes=["owner", "shared"])
    assert svc.get_document(d.id, scopes=None).id == d.id


def test_recency_tiebreak_and_since_filter(tmp_path):
    from datetime import UTC, datetime

    from companion_core.clock import FakeClock

    clock = FakeClock(datetime(2026, 10, 1, 9, 0, tzinfo=UTC))
    svc = VaultService(Database(tmp_path / "v.db"), clock=clock)
    svc.migrate()
    old = svc.create_note(NoteCreate(text="Weekly plan: review the Python lesson notes."), actor="desk")
    clock.advance(days=1)
    new = svc.create_note(NoteCreate(text="Weekly plan: review the Python lesson notes again."), actor="desk")
    hits = svc.search(SearchRequest(query="weekly plan python lesson"), scopes=["owner"]).hits
    assert {h.document_id for h in hits} == {old.id, new.id}
    later = svc.search(SearchRequest(query="weekly plan python lesson", since=new.created_at), scopes=["owner"]).hits
    assert [h.document_id for h in later] == [new.id]
