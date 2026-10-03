"""Course model: lessons with objectives, explanation, checked examples, exercises and hints.

Content is curated and references the official Python tutorial (docs.python.org). Every
example carries its expected output and is executed by the test suite, so what the tutor
shows is what Python actually prints.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Example(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    output: str
    note: str = ""


class Check(BaseModel):
    """A static check on submitted code (never executed by the tutor). ``kind``:
    requires_node (an ast node type must appear), requires_call (a function must be called),
    forbids_node, defines_function (name), output_equals (user-reported output must match),
    contains_text (source contains text)."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["requires_node", "requires_call", "forbids_node", "defines_function", "output_equals", "contains_text"]
    value: str
    message: str


class Exercise(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    prompt: str
    starter: str = ""
    checks: list[Check]
    hints: list[str] = Field(default_factory=list)
    solution_notes: str = ""
    topics: list[str] = Field(default_factory=list)
    expected_output: str | None = None


class Lesson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    objectives: list[str]
    explanation: str
    examples: list[Example]
    exercises: list[Exercise]
    topics: list[str]
    references: list[str] = Field(default_factory=list)
    next_steps: str = ""
    minutes: int = 30


class Course(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    description: str
    lessons: list[Lesson]
    language: str = "python"

    def lesson(self, lesson_id: str) -> Lesson | None:
        return next((lesson for lesson in self.lessons if lesson.id == lesson_id), None)

    def index_of(self, lesson_id: str) -> int:
        return next((i for i, lesson in enumerate(self.lessons) if lesson.id == lesson_id), -1)
