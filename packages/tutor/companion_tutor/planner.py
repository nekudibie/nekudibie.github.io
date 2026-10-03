"""Course proposals and adaptive lesson selection.

A proposal is just data until the user accepts it; only then are schedules created (by the
API, in the scheduler). Progress drives what comes next: lessons marked needs_review come
back before new material, and weak topics get their exercises repeated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .course import Course, Lesson

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass
class Proposal:
    id: str
    title: str
    days: list[int]
    time_local: str
    lessons_per_week: int
    weeks: int
    description: str
    rule: dict[str, Any] = field(default_factory=dict)


def propose(course: Course, *, goal: str = "", preferred_days: list[int] | None = None, time_local: str = "19:30") -> list[Proposal]:
    """Three honest options; the user picks one (or none)."""
    n = len(course.lessons)
    options = []
    days3 = preferred_days[:3] if preferred_days else [0, 2, 4]
    days2 = preferred_days[:2] if preferred_days else [1, 3]
    days5 = preferred_days[:5] if preferred_days and len(preferred_days) >= 5 else [0, 1, 2, 3, 4]
    for pid, days, label in (("steady", days3, "Steady"), ("light", days2, "Light"), ("intensive", days5, "Intensive")):
        per_week = len(days)
        weeks = -(-n // per_week)
        options.append(Proposal(
            id=pid, title=f"{label}: {per_week} lesson{'s' if per_week != 1 else ''} a week at {time_local}",
            days=days, time_local=time_local, lessons_per_week=per_week, weeks=weeks,
            description=f"{', '.join(DAY_NAMES[d] for d in days)} at {time_local}; {n} lessons in about {weeks} week{'s' if weeks != 1 else ''}, 30 minutes each."
            + (f" Goal noted: {goal.strip()}." if goal.strip() else ""),
            rule={"type": "weekly", "days": days, "time_local": time_local},
        ))
    return options


def choose_next(course: Course, progress: list[Any]) -> tuple[Lesson | None, str]:
    """Return (lesson, reason). ``progress`` rows have lesson_id, status, weak_topics."""
    by_id = {p.lesson_id: p for p in progress}
    for lesson in course.lessons:
        p = by_id.get(lesson.id)
        if p is not None and p.status == "needs_review":
            return lesson, f"Review first: {lesson.title} needs another go" + (f" (weak: {', '.join(p.weak_topics)})" if p.weak_topics else "") + "."
    for lesson in course.lessons:
        p = by_id.get(lesson.id)
        if p is None or p.status in {"not_started", "in_progress"}:
            return lesson, ("Continue" if p is not None else "Start") + f" {lesson.title}."
    return None, "Every lesson is mastered. Next steps: " + (course.lessons[-1].next_steps or "pick a project.")


def adapt_explanation(lesson: Lesson, weak_topics: list[str]) -> str:
    """Prepend a focused note when the learner struggled with topics this lesson covers."""
    overlap = [t for t in lesson.topics if t in set(weak_topics)]
    if not overlap:
        return lesson.explanation
    return f"Focus for you: take {', '.join(overlap)} slowly; try each example by hand before reading the output.\n\n" + lesson.explanation
