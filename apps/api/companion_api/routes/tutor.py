"""Tutor endpoints: course, adaptive next lesson, static exercise checks, progress, plans.

Schedules are created only by ``POST /v1/tutor/plan/accept``; proposing is side-effect free.
"""

from __future__ import annotations

from typing import Annotated, Any

from companion_core.auth import ClientIdentity, Permission
from companion_core.errors import NotFound, ValidationFailed
from companion_tutor import (
    COURSES,
    adapt_explanation,
    check_submission,
    choose_next,
    next_hint,
    propose,
)
from companion_worker.scheduler import Rule
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth import require

router = APIRouter(prefix="/v1/tutor")
Learner = Annotated[ClientIdentity, Depends(require(Permission.TUTOR_USE))]
DEFAULT_COURSE = "python-basics"


class AttemptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: str = DEFAULT_COURSE
    lesson_id: str
    exercise_id: str
    code: str = Field(max_length=20000)
    output: str | None = Field(default=None, max_length=5000, description="What your code printed when you ran it")


class ProposeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: str = DEFAULT_COURSE
    goal: str = Field(default="", max_length=500)
    preferred_days: list[int] | None = None
    time_local: str = Field(default="19:30", pattern=r"^\d{2}:\d{2}$")


class AcceptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: str = DEFAULT_COURSE
    proposal_id: str = Field(pattern=r"^(steady|light|intensive|custom)$")
    days: list[int] | None = None
    time_local: str = Field(default="19:30", pattern=r"^\d{2}:\d{2}$")


def _course(course_id: str) -> Any:
    c = COURSES.get(course_id)
    if c is None:
        raise NotFound(f"course {course_id} not found")
    return c


async def _progress(request: Request, identity: ClientIdentity, course_id: str) -> Any:
    return await request.app.state.companion.vault.progress(course_id, scopes=identity.memory_scopes)


@router.get("/course")
async def course(identity: Learner, request: Request, course_id: str = DEFAULT_COURSE):
    c = _course(course_id)
    prog = {p.lesson_id: p for p in await _progress(request, identity, course_id)}
    return {
        "course": {"id": c.id, "title": c.title, "description": c.description, "language": c.language},
        "lessons": [{"id": lsn.id, "title": lsn.title, "objectives": lsn.objectives, "topics": lsn.topics, "minutes": lsn.minutes, "exercises": len(lsn.exercises),
                     "status": prog[lsn.id].status if lsn.id in prog else "not_started", "attempts": prog[lsn.id].attempts if lsn.id in prog else 0} for lsn in c.lessons],
        "summary": _summary(c, list(prog.values())),
    }


def _summary(c: Any, prog: list[Any]) -> dict[str, Any]:
    mastered = sum(1 for p in prog if p.status == "mastered")
    review = [p.lesson_id for p in prog if p.status == "needs_review"]
    weak = sorted({t for p in prog for t in p.weak_topics})
    return {"lessons": len(c.lessons), "mastered": mastered, "needs_review": review, "weak_topics": weak, "attempts": sum(p.attempts for p in prog)}


@router.get("/next")
async def next_lesson(identity: Learner, request: Request, course_id: str = DEFAULT_COURSE):
    c = _course(course_id)
    prog = await _progress(request, identity, course_id)
    lesson, reason = choose_next(c, prog)
    return {"lesson": _lesson_view(lesson, prog) if lesson else None, "reason": reason}


def _lesson_view(lesson: Any, prog: list[Any]) -> dict[str, Any]:
    p = next((x for x in prog if x.lesson_id == lesson.id), None)
    weak = p.weak_topics if p else []
    attempts_by_ex: dict[str, int] = {}
    if p:
        for e in p.evidence:
            attempts_by_ex[e["exercise_id"]] = attempts_by_ex.get(e["exercise_id"], 0) + 1
    return {
        "id": lesson.id, "title": lesson.title, "objectives": lesson.objectives, "explanation": adapt_explanation(lesson, weak),
        "examples": [e.model_dump() for e in lesson.examples],
        "exercises": [{"id": e.id, "prompt": e.prompt, "starter": e.starter, "topics": e.topics, "hints_available": len(e.hints), "attempts": attempts_by_ex.get(e.id, 0),
                       "needs_output": any(ch.kind == "output_equals" for ch in e.checks)} for e in lesson.exercises],
        "topics": lesson.topics, "references": lesson.references, "next_steps": lesson.next_steps, "minutes": lesson.minutes,
        "progress": p.model_dump() if p else None,
    }


@router.get("/lessons/{lesson_id}")
async def lesson(lesson_id: str, identity: Learner, request: Request, course_id: str = DEFAULT_COURSE):
    c = _course(course_id)
    lsn = c.lesson(lesson_id)
    if lsn is None:
        raise NotFound(f"lesson {lesson_id} not found")
    return _lesson_view(lsn, await _progress(request, identity, course_id))


@router.post("/attempts")
async def attempt(body: AttemptBody, identity: Learner, request: Request):
    st = request.app.state.companion
    c = _course(body.course_id)
    lsn = c.lesson(body.lesson_id)
    if lsn is None:
        raise NotFound(f"lesson {body.lesson_id} not found")
    ex = next((e for e in lsn.exercises if e.id == body.exercise_id), None)
    if ex is None:
        raise NotFound(f"exercise {body.exercise_id} not found")
    result = check_submission(ex, body.code, reported_output=body.output)
    progress = await st.vault.record_attempt(body.course_id, body.lesson_id, exercise_id=body.exercise_id, passed=result.passed, score=result.score, topics=ex.topics, actor=identity.client_id)
    failed_attempts = sum(1 for e in progress.evidence if e["exercise_id"] == body.exercise_id and not e["passed"])
    hint = None if result.passed else next_hint(ex, failed_attempts)
    return {"result": result.__dict__, "progress": progress.model_dump(), "hint": hint, "solution_notes": ex.solution_notes if result.passed else None}


@router.get("/progress")
async def progress(identity: Learner, request: Request, course_id: str = DEFAULT_COURSE):
    c = _course(course_id)
    prog = await _progress(request, identity, course_id)
    return {"progress": [p.model_dump() for p in prog], "summary": _summary(c, prog)}


@router.post("/plan/propose")
async def plan_propose(body: ProposeBody, identity: Learner, request: Request):
    c = _course(body.course_id)
    if body.preferred_days and any(d < 0 or d > 6 for d in body.preferred_days):
        raise ValidationFailed("days are 0 (Monday) to 6 (Sunday)")
    return {"proposals": [p.__dict__ for p in propose(c, goal=body.goal, preferred_days=body.preferred_days, time_local=body.time_local)], "note": "Nothing is scheduled until you accept one."}


@router.post("/plan/accept", status_code=201)
async def plan_accept(body: AcceptBody, identity: Annotated[ClientIdentity, Depends(require(Permission.SCHEDULE_WRITE))], request: Request):
    st = request.app.state.companion
    if not identity.has(Permission.TUTOR_USE):
        raise ValidationFailed("this client cannot use the tutor")
    c = _course(body.course_id)
    if body.proposal_id == "custom":
        if not body.days:
            raise ValidationFailed("custom plans need days")
        days = sorted(set(body.days))
    else:
        chosen = next(p for p in propose(c, time_local=body.time_local) if p.id == body.proposal_id)
        days = chosen.days
    existing = [s for s in st.scheduler.list(client_id=identity.client_id, status=["active", "paused"], kind="lesson") if s.payload.get("course_id") == c.id]
    for s in existing:
        st.scheduler.set_status(s.id, "cancelled")
    sch = st.scheduler.create(
        client_id=identity.client_id, kind="lesson", title=f"Python lesson: {c.title}", body="Open the Learn page for today's lesson.",
        rule=Rule(type="weekly", days=days, time_local=body.time_local), timezone=st.config.instance.timezone, payload={"course_id": c.id},
    )
    return {"schedule": sch.model_dump(), "replaced": [s.id for s in existing]}


@router.get("/plan")
async def plan(identity: Learner, request: Request):
    st = request.app.state.companion
    return [s.model_dump() for s in st.scheduler.list(client_id=identity.client_id, status=["active", "paused"], kind="lesson")]
