from __future__ import annotations

import pytest
from companion_api.memory_extractor import extract_candidates
from companion_core.db import Database
from companion_core.errors import Conflict, NotFound
from companion_vault.service import VaultService
from companion_vault.structured import ActionCreate, DecisionCreate, FactCreate, PurchaseUpsert


@pytest.fixture
def sm(tmp_path):
    svc = VaultService(Database(tmp_path / "v.db"))
    svc.migrate()
    return svc.structured


def test_confirmed_value_supersedes_and_keeps_history(sm):
    a = sm.add_fact(FactCreate(subject="owner", predicate="favourite tea", value="Earl Grey"), actor="desk")
    b = sm.update_fact(a.id, "Assam", actor="desk", reason="changed")
    assert [(f.value, f.status) for f in sm.fact_history(a.id)] == [("Earl Grey", "superseded"), ("Assam", "confirmed")]
    assert sm.get_fact(a.id).valid_to is not None and b.supersedes_id == a.id
    assert [f.value for f in sm.current_facts(scopes=["owner"])] == ["Assam"]
    with pytest.raises(Conflict):
        sm.update_fact(a.id, "Darjeeling", actor="desk")  # superseded rows are frozen


def test_candidates_are_separate_until_confirmed(sm):
    c = sm.add_fact(FactCreate(subject="owner", predicate="lives in", value="Leeds", status="candidate", confidence=0.4, trust="inferred", evidence_message_id="msg_1"), actor="extractor")
    assert sm.current_facts(scopes=["owner"]) == []
    assert sm.search_facts("where do I live", scopes=["owner"]) == []
    assert [f.id for f in sm.candidates(scopes=["owner"])] == [c.id]
    confirmed = sm.confirm_fact(c.id, actor="desk")
    assert confirmed.status == "confirmed" and confirmed.trust == "owner_stated" and confirmed.confidence == 1.0
    assert sm.search_facts("lives in", scopes=["owner"])[0].value == "Leeds"
    with pytest.raises(Conflict):
        sm.reject_fact(c.id, actor="desk")
    r = sm.retract_fact(c.id, actor="desk", reason="moved")
    assert r.status == "retracted" and sm.current_facts(scopes=["owner"]) == []


def test_candidate_rejection_and_scope(sm):
    c = sm.add_fact(FactCreate(subject="owner", predicate="dog", value="Biscuit", status="candidate", scope="owner"), actor="extractor")
    assert sm.candidates(scopes=["shared"]) == []
    with pytest.raises(NotFound):
        sm.get_fact(c.id, scopes=["shared"])
    assert sm.reject_fact(c.id, actor="desk", reason="no dog").status == "rejected"
    assert sm.candidates(scopes=["owner"]) == []


def test_decisions_supersede_and_search(sm):
    d1 = sm.record_decision(DecisionCreate(statement="Use FTS5 first", project="Lantern"), actor="desk")
    d2 = sm.supersede_decision(d1.id, DecisionCreate(statement="Use FTS5 plus local embeddings", rationale="evaluation showed a gain"), actor="desk")
    assert d2.project_name == "Lantern" and d2.supersedes_id == d1.id
    assert sm.get_decision(d1.id).status == "superseded"
    current = sm.list_decisions(scopes=["owner"], project="lantern")
    assert [d.id for d in current] == [d2.id]
    assert [d.id for d in sm.search_decisions("lantern embeddings", scopes=["owner"])] == [d2.id]
    with pytest.raises(Conflict):
        sm.supersede_decision(d1.id, DecisionCreate(statement="x"), actor="desk")
    rev = sm.reverse_decision(d2.id, actor="desk", reason="dropped")
    assert rev.status == "reversed" and sm.list_decisions(scopes=["owner"]) == []
    assert len(sm.list_decisions(scopes=["owner"], include_history=True)) == 2


def test_actions_keep_uncertainty(sm):
    a = sm.create_action(ActionCreate(title="Send the budget sheet", due_text="by Friday", due_confidence=0.6, meeting_id="rec_1", source_segment_id="seg_12", source_quote="Neku, can you send the budget sheet by Friday?"), actor="worker")
    assert a.status == "draft" and a.owner is None and a.due_at is None and a.due_text == "by Friday"
    opened = sm.update_action(a.id, actor="desk", status="open", owner="Neku", owner_confidence=1.0, due_at="2026-10-09")
    assert opened.status == "open" and opened.owner == "Neku"
    done = sm.update_action(a.id, actor="desk", status="done")
    assert done.completed_at is not None
    assert [x.id for x in sm.list_actions(scopes=["owner"], meeting_id="rec_1")] == [a.id]
    assert sm.list_actions(scopes=["owner"], status=["open"]) == []
    with pytest.raises(Exception, match="cannot update"):
        sm.update_action(a.id, actor="desk", meeting_id="other")


def test_purchase_dedup_and_status_transitions(sm):
    p, o = sm.upsert_purchase(PurchaseUpsert(merchant="Amazon", order_ref="203-5567", items=[{"name": "USB mic"}], amount=39.99, currency="GBP", source_message_id="m1"), actor="w")
    assert o == "created" and p.status == "confirmed"
    p, o = sm.upsert_purchase(PurchaseUpsert(merchant="AMAZON ", order_ref="203-5567", status="shipped", source_message_id="m2"), actor="w")
    assert o == "updated" and p.status == "shipped" and p.amount == 39.99 and p.items == [{"name": "USB mic"}]
    p, o = sm.upsert_purchase(PurchaseUpsert(merchant="Amazon", order_ref="203-5567", status="confirmed", source_message_id="m1"), actor="w")
    assert o == "duplicate"
    # a late "confirmed" email must not regress a shipped order
    p, o = sm.upsert_purchase(PurchaseUpsert(merchant="Amazon", order_ref="203-5567", status="confirmed", source_message_id="m3"), actor="w")
    assert p.status == "shipped" and len(p.status_history) == 3
    p, o = sm.upsert_purchase(PurchaseUpsert(merchant="Amazon", order_ref="203-5567", status="refunded", source_message_id="m4"), actor="w")
    assert p.status == "refunded"
    p, o = sm.upsert_purchase(PurchaseUpsert(merchant="Amazon", order_ref="203-5567", status="delivered", source_message_id="m5"), actor="w")
    assert p.status == "refunded"  # terminal state wins
    assert [x.order_ref for x in sm.list_purchases(scopes=["owner"], merchant="amazon")] == ["203-5567"]


def test_lesson_progress_from_attempts(sm):
    lp = sm.record_attempt("py", "l1", exercise_id="e1", passed=False, score=0.2, topics=["loops"], actor="desk")
    assert lp.status == "in_progress" and lp.weak_topics == ["loops"]
    lp = sm.record_attempt("py", "l1", exercise_id="e1", passed=False, score=0.3, topics=["loops"], actor="desk")
    assert lp.status == "needs_review"
    lp = sm.record_attempt("py", "l1", exercise_id="e1", passed=True, score=1.0, topics=["loops"], actor="desk")
    lp = sm.record_attempt("py", "l1", exercise_id="e2", passed=True, score=0.9, topics=["loops"], actor="desk")
    assert lp.status == "mastered" and lp.attempts == 4 and lp.correct == 2 and len(lp.evidence) == 4
    assert sm.progress("py", scopes=["owner"])[0].lesson_id == "l1"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("My favourite tea is Earl Grey, by the way.", [("favourite tea", "Earl Grey")]),
        ("I live in Leeds and I work at Northgate Labs.", [("lives in", "Leeds"), ("works at", "Northgate Labs")]),
        ("I prefer dark mode on every screen", [("preference", "dark mode on every screen")]),
        ("Remember that my favourite tea is Assam", []),  # explicit -> tool path, not a candidate
        ("What time is it?", []),
        ("I'm allergic to penicillin.", [("allergy", "penicillin")]),
    ],
)
def test_extractor_patterns(text, expected):
    got = [(c.predicate, c.value) for c in extract_candidates(text)]
    assert got == expected
    for c in extract_candidates(text):
        assert c.subject == "owner" and c.confidence < 1 and c.value in c.quote
