from __future__ import annotations

import contextlib
import io

import pytest
from companion_tutor import PYTHON_BASICS, check_submission, choose_next, next_hint, propose
from companion_tutor.planner import adapt_explanation


@pytest.mark.parametrize("lesson", PYTHON_BASICS.lessons, ids=lambda lsn: lsn.id)
def test_every_example_prints_its_stated_output(lesson):
    for ex in lesson.examples:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exec(ex.code, {})  # noqa: S102 - curated course content checked at test time, never user code
        assert buf.getvalue().strip() == ex.output.strip(), (lesson.id, ex.code)


def test_lessons_are_complete():
    for lesson in PYTHON_BASICS.lessons:
        assert lesson.objectives and lesson.explanation and lesson.examples and lesson.exercises and lesson.references
        for ex in lesson.exercises:
            assert ex.checks and ex.hints and ex.topics


def test_checker_feedback_without_execution():
    ex = PYTHON_BASICS.lesson("l4-loops").exercises[0]  # sum of even numbers below 100
    bad = check_submission(ex, "total = 0\nfor n in range(0, 101, 2):\n    total += n\nprint(total)", reported_output="2550")
    assert not bad.passed and any("2450" in f for f in bad.feedback) and bad.method.startswith("static")
    syntax = check_submission(ex, "for n in range(10)\n    print(n)")
    assert syntax.syntax_error and "line 1" in syntax.syntax_error and not syntax.passed
    no_output = check_submission(ex, "total = sum(range(0, 100, 2))\nprint(total)")
    assert not no_output.passed and any("paste what it prints" in f for f in no_output.feedback) and "Use a for loop." in no_output.failed_checks
    good = check_submission(ex, "total = 0\nfor n in range(0, 100, 2):\n    total += n\nprint(total)", reported_output="2450\n")
    assert good.passed and good.score == 1.0 and good.output_checked
    assert check_submission(ex, "   ").feedback[0].startswith("There is no code")


def test_forbidden_bare_except_and_function_definition_checks():
    files = PYTHON_BASICS.lesson("l8-files-errors").exercises[0]
    bare = check_submission(files, "try:\n    with open('notes.txt') as f:\n        print(len(f.readlines()))\nexcept:\n    print('notes.txt not found')")
    assert not bare.passed and any("bare except" in f for f in bare.feedback)
    ok = check_submission(files, "try:\n    with open('notes.txt') as f:\n        print(len(f.readlines()))\nexcept FileNotFoundError:\n    print('notes.txt not found')")
    assert ok.passed
    fn = PYTHON_BASICS.lesson("l6-functions").exercises[0]
    r = check_submission(fn, "def celsius_to_fahrenheit(c):\n    print(c * 9 / 5 + 32)\ncelsius_to_fahrenheit(20)", reported_output="68.0")
    assert not r.passed and any("Return the value" in f for f in r.feedback)


def test_hints_are_revealed_progressively():
    ex = PYTHON_BASICS.lesson("l4-loops").exercises[0]
    assert next_hint(ex, 0) is None
    assert next_hint(ex, 1) == ex.hints[0]
    assert next_hint(ex, 2) == ex.hints[1]
    assert next_hint(ex, 99) == ex.hints[-1]


class _P:
    def __init__(self, lesson_id, status, weak=()):  # type: ignore[no-untyped-def]
        self.lesson_id, self.status, self.weak_topics = lesson_id, status, list(weak)


def test_next_lesson_prefers_review_then_first_unfinished():
    c = PYTHON_BASICS
    lesson, reason = choose_next(c, [])
    assert lesson.id == c.lessons[0].id and reason.startswith("Start")
    lesson, reason = choose_next(c, [_P("l1-numbers-strings", "mastered"), _P("l2-variables-strings", "in_progress")])
    assert lesson.id == "l2-variables-strings" and reason.startswith("Continue")
    lesson, reason = choose_next(c, [_P("l1-numbers-strings", "mastered"), _P("l2-variables-strings", "mastered"), _P("l3-lists", "needs_review", ["lists"]), _P("l4-loops", "in_progress")])
    assert lesson.id == "l3-lists" and "Review first" in reason and "lists" in reason
    lesson, reason = choose_next(c, [_P(lsn.id, "mastered") for lsn in c.lessons])
    assert lesson is None and "mastered" in reason
    assert adapt_explanation(c.lesson("l4-loops"), ["loops"]).startswith("Focus for you: take loops")
    assert adapt_explanation(c.lesson("l4-loops"), ["dicts"]) == c.lesson("l4-loops").explanation


def test_proposals_are_data_not_schedules():
    props = propose(PYTHON_BASICS, goal="automate my notes", preferred_days=[1, 3], time_local="07:15")
    assert [p.id for p in props] == ["steady", "light", "intensive"]
    light = props[1]
    assert light.days == [1, 3] and light.time_local == "07:15" and light.weeks == 4 and light.rule == {"type": "weekly", "days": [1, 3], "time_local": "07:15"}
    assert "automate my notes" in light.description
