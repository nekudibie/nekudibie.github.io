"""Lesson planning, exercises and progress tracking (code is read, never executed here)."""

from .checker import CheckResult, check_submission, next_hint
from .content import COURSES, PYTHON_BASICS
from .course import Course, Exercise, Lesson
from .planner import Proposal, adapt_explanation, choose_next, propose

__all__ = ["COURSES", "PYTHON_BASICS", "CheckResult", "Course", "Exercise", "Lesson", "Proposal", "adapt_explanation", "check_submission", "choose_next", "next_hint", "propose"]
