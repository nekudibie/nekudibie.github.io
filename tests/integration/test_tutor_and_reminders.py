from __future__ import annotations

from datetime import UTC, datetime

from companion_core.clock import FakeClock

from tests.conftest import ADMIN, DESK, GUEST, ROVER, new_conversation, sse, text_of


def test_course_and_adaptive_flow(client):
    c = client.get("/v1/tutor/course", headers=DESK).json()
    assert c["course"]["id"] == "python-basics" and len(c["lessons"]) == 8 and c["summary"]["mastered"] == 0
    nxt = client.get("/v1/tutor/next", headers=DESK).json()
    assert nxt["lesson"]["id"] == "l1-numbers-strings" and nxt["reason"].startswith("Start")
    # a wrong attempt: feedback, a first hint, progress recorded from the attempt
    r = client.post("/v1/tutor/attempts", json={"lesson_id": "l1-numbers-strings", "exercise_id": "e1", "code": "minutes = 24 * 60\nprint('A day has ' + str(minutes) + ' minutes')", "output": "A day has 1440 minutes"}, headers=DESK).json()
    assert r["result"]["passed"] is False and any("f-string" in f for f in r["result"]["feedback"]) and r["hint"] == "An f-string starts with f and uses {curly braces} for values."
    assert r["progress"]["attempts"] == 1 and r["progress"]["status"] == "in_progress"
    r = client.post("/v1/tutor/attempts", json={"lesson_id": "l1-numbers-strings", "exercise_id": "e1", "code": "minutes = 24 * 60\nprint('A day has ' + str(minutes) + ' minutes')", "output": "A day has 1440 minutes"}, headers=DESK).json()
    assert r["progress"]["status"] == "needs_review" and r["hint"] == "24 * 60 is 1440; keep the arithmetic in the variable, not in the text."
    # the tutor now adapts: review first, with a focus note
    nxt = client.get("/v1/tutor/next", headers=DESK).json()
    assert "Review first" in nxt["reason"] and nxt["lesson"]["explanation"].startswith("Focus for you")
    good = "minutes = 24 * 60\nprint(f'A day has {minutes} minutes')"
    for _ in range(2):
        r = client.post("/v1/tutor/attempts", json={"lesson_id": "l1-numbers-strings", "exercise_id": "e1", "code": good, "output": "A day has 1440 minutes"}, headers=DESK).json()
    assert r["result"]["passed"] and r["progress"]["status"] == "mastered" and r["hint"] is None
    nxt = client.get("/v1/tutor/next", headers=DESK).json()
    assert nxt["lesson"]["id"] == "l2-variables-strings"
    prog = client.get("/v1/tutor/progress", headers=DESK).json()
    assert prog["summary"]["mastered"] == 1 and prog["summary"]["attempts"] == 4
    assert client.get("/v1/tutor/course", headers=GUEST).status_code == 403
    assert client.post("/v1/tutor/attempts", json={"lesson_id": "nope", "exercise_id": "e1", "code": "x"}, headers=DESK).status_code == 404


def test_plan_is_only_scheduled_after_acceptance(cfg, make_client):
    clock = FakeClock(datetime(2026, 10, 23, 12, 0, tzinfo=UTC))  # Friday
    client = make_client(clock=clock)
    props = client.post("/v1/tutor/plan/propose", json={"goal": "build a notes tool", "preferred_days": [0, 3], "time_local": "19:30"}, headers=DESK).json()
    assert len(props["proposals"]) == 3 and "Nothing is scheduled" in props["note"]
    assert client.get("/v1/tutor/plan", headers=DESK).json() == [] and client.get("/v1/schedules", headers=DESK).json() == []
    acc = client.post("/v1/tutor/plan/accept", json={"proposal_id": "light", "time_local": "19:30"}, headers=DESK).json()
    sch = acc["schedule"]
    rule = {k: v for k, v in sch["rule"].items() if v is not None}
    assert sch["kind"] == "lesson" and rule == {"type": "weekly", "days": [1, 3], "time_local": "19:30"} and sch["timezone"] == "Europe/London"
    assert sch["next_run_at"] == "2026-10-27T19:30:00.000Z"  # Tuesday 19:30 GMT (clocks went back on the 25th)
    # accepting again replaces rather than duplicates
    acc2 = client.post("/v1/tutor/plan/accept", json={"proposal_id": "steady", "time_local": "08:00"}, headers=DESK).json()
    assert acc2["replaced"] == [sch["id"]] and len(client.get("/v1/tutor/plan", headers=DESK).json()) == 1
    # the reminder fires from the server clock, survives a 'restart' (new tick), and is acknowledged once
    clock.set(datetime(2026, 10, 26, 8, 1, tzinfo=UTC))  # Monday 08:01 GMT
    fired = client.post("/v1/reminders/tick", headers=ADMIN).json()
    assert len(fired) == 1 and fired[0]["kind"] == "lesson" and fired[0]["payload"] == {"course_id": "python-basics"}
    assert client.post("/v1/reminders/tick", headers=ADMIN).json() == []
    pend = client.get("/v1/reminders/pending", headers=DESK).json()
    assert [p["id"] for p in pend] == [fired[0]["id"]]
    assert client.get("/v1/reminders/pending", headers=ROVER).json() == []  # not this client's
    sn = client.post(f"/v1/reminders/{fired[0]['id']}/snooze", json={"minutes": 5}, headers=DESK).json()
    assert sn["status"] == "snoozed"
    clock.advance(minutes=6)
    assert len(client.post("/v1/reminders/tick", headers=ADMIN).json()) == 1
    assert client.post(f"/v1/reminders/{fired[0]['id']}/ack", headers=DESK).json()["status"] == "acknowledged"
    assert client.get("/v1/reminders/pending", headers=DESK).json() == []
    assert client.post("/v1/schedules", json={"title": "x", "rule": {"type": "daily", "time_local": "09:00"}}, headers=GUEST).status_code == 403


def test_tutor_through_chat_never_schedules_by_itself(client):
    cid = new_conversation(client)
    events = sse(client, cid, "Teach me Python please")
    out = text_of(events)
    assert "Options:" in out and "nothing is scheduled until you choose" in out.lower()
    assert [d for t, d in events if t == "ui"][0]["payload"]["intent"] == "choose_plan"
    assert client.get("/v1/schedules", headers=DESK).json() == []
    out = text_of(sse(client, cid, "What's my next lesson?"))
    assert "Numbers, strings and print" in out
    out = text_of(sse(client, cid, "How am I doing with Python?"))
    assert "mastered 0 of 8" in out


def test_reminder_schedule_crud_and_dst(cfg, make_client):
    clock = FakeClock(datetime(2026, 3, 27, 12, 0, tzinfo=UTC))  # before the spring clock change on 29 March
    client = make_client(clock=clock)
    sch = client.post("/v1/schedules", json={"title": "Stretch", "rule": {"type": "daily", "time_local": "07:00"}}, headers=DESK).json()
    assert sch["next_run_at"] == "2026-03-28T07:00:00.000Z"  # GMT
    clock.set(datetime(2026, 3, 28, 7, 1, tzinfo=UTC))
    client.post("/v1/reminders/tick", headers=ADMIN)
    after = client.get("/v1/schedules", headers=DESK).json()[0]
    assert after["next_run_at"] == "2026-03-29T06:00:00.000Z"  # 07:00 BST: wall-clock time preserved
    paused = client.post(f"/v1/schedules/{sch['id']}/pause", headers=DESK).json()
    assert paused["status"] == "paused"
    moved = client.post(f"/v1/schedules/{sch['id']}/reschedule", json={"rule": {"type": "weekly", "days": [5], "time_local": "10:00"}}, headers=DESK).json()
    assert moved["status"] == "active" and moved["rule"]["days"] == [5]
    assert client.post(f"/v1/schedules/{sch['id']}/cancel", headers=DESK).json()["status"] == "cancelled"
    from tests.conftest import auth

    assert client.post(f"/v1/schedules/{sch['id']}/pause", headers=ROVER).status_code == 403  # rover may not write schedules at all
    assert client.post(f"/v1/schedules/{sch['id']}/pause", headers=auth("limited-desk-token-0123456789")).status_code == 404  # another desk client cannot see it
