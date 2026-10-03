"""Static exercise checking: the tutor reads the code, it does not run it.

Checks parse the submission with ``ast`` (syntax errors are feedback, not crashes) and
compare user-reported output when the exercise asks for it. Automated execution would need
the separate restricted sandbox described in docs/SECURITY.md; until that exists, results
are labelled "static check" so nobody mistakes them for a test run.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from .course import Check, Exercise


@dataclass
class CheckResult:
    passed: bool
    score: float
    feedback: list[str] = field(default_factory=list)
    passed_checks: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    syntax_error: str | None = None
    method: str = "static check (code read, not executed)"
    output_checked: bool = False


_NODE_ALIASES = {"BareExcept": None}


def _has_node(tree: ast.AST, name: str) -> bool:
    if name == "BareExcept":
        return any(isinstance(n, ast.ExceptHandler) and n.type is None for n in ast.walk(tree))
    cls = getattr(ast, name, None)
    return cls is not None and any(isinstance(n, cls) for n in ast.walk(tree))


def _calls(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


def _functions(tree: ast.AST) -> set[str]:
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}


def _norm_out(s: str) -> str:
    return "\n".join(line.rstrip() for line in s.strip().replace("\r\n", "\n").split("\n"))


def check_submission(exercise: Exercise, code: str, *, reported_output: str | None = None) -> CheckResult:
    result = CheckResult(passed=False, score=0.0)
    if not code.strip():
        result.feedback.append("There is no code yet. Start from the prompt and write a first version.")
        return result
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        result.syntax_error = f"line {exc.lineno}: {exc.msg}"
        result.feedback.append(f"Python cannot read this yet: syntax error at line {exc.lineno} ({exc.msg}). Check brackets, quotes and the colon at the end of def/for/if lines.")
        return result
    calls = _calls(tree)
    funcs = _functions(tree)
    total = len(exercise.checks)
    for c in exercise.checks:
        ok = _run_check(c, tree, code, calls, funcs, reported_output)
        if ok is None:
            total -= 1  # output check skipped: no output reported
            result.feedback.append("Run your code and paste what it prints so the output can be checked too.")
            continue
        (result.passed_checks if ok else result.failed_checks).append(c.message)
        if not ok:
            result.feedback.append(c.message)
        if c.kind == "output_equals":
            result.output_checked = True
    result.score = len(result.passed_checks) / total if total else 0.0
    result.passed = not result.failed_checks and total > 0 and (result.output_checked or not any(c.kind == "output_equals" for c in exercise.checks))
    if result.passed:
        result.feedback.insert(0, "All checks pass." + (" The output you reported matches." if result.output_checked else ""))
    return result


def _run_check(c: Check, tree: ast.AST, code: str, calls: set[str], funcs: set[str], reported_output: str | None) -> bool | None:
    if c.kind == "requires_node":
        return _has_node(tree, c.value)
    if c.kind == "forbids_node":
        return not _has_node(tree, c.value)
    if c.kind == "requires_call":
        return c.value in calls
    if c.kind == "defines_function":
        return c.value in funcs
    if c.kind == "contains_text":
        return c.value in code
    if c.kind == "output_equals":
        if reported_output is None:
            return None
        return _norm_out(reported_output) == _norm_out(c.value)
    return False


def next_hint(exercise: Exercise, attempts_so_far: int) -> str | None:
    """Reveal one more hint per failed attempt; never all at once."""
    if not exercise.hints or attempts_so_far <= 0:
        return None
    return exercise.hints[min(attempts_so_far, len(exercise.hints)) - 1]
