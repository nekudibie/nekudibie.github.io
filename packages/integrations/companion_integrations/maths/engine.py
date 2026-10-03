"""Maths on a tight leash.

The input is tokenised against an allowlist (numbers, operators, brackets, commas, '=',
single-letter variables and a fixed set of function/constant names) *before* it reaches
SymPy's parser, whose global namespace is restricted (no builtins). Results are exact where
SymPy can be exact, with a decimal approximation alongside. Explanations are short
descriptions of what was done, not a claim of a full derivation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from companion_core.errors import ValidationFailed

_ALLOWED_FUNCS = {"sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh", "sqrt", "cbrt", "log", "ln", "exp", "abs", "factorial", "floor", "ceiling", "root"}
_ALLOWED_CONSTS = {"pi", "e", "E", "I", "oo"}
_TOKEN_RE = re.compile(r"\s*(?:(\d+\.\d*|\.\d+|\d+)|([A-Za-z_][A-Za-z_0-9]*)|(\*\*|[-+*/^(),=!]))")
MAX_LEN = 400
MAX_EXPONENT = 2000


@dataclass
class MathsResult:
    task: str
    input: str
    parsed: str
    result: str
    approx: str | None = None
    variable: str | None = None
    steps: list[str] = field(default_factory=list)
    explanation: str = ""
    ok: bool = True


def tokenise(text: str) -> list[str]:
    if len(text) > MAX_LEN:
        raise ValidationFailed(f"expression longer than {MAX_LEN} characters")
    pos = 0
    out: list[str] = []
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m or m.end() == pos:
            raise ValidationFailed(f"unexpected character {text[pos:pos + 1]!r} at position {pos}")
        num, name, op = m.groups()
        if name is not None:
            if not (name in _ALLOWED_FUNCS or name in _ALLOWED_CONSTS or (len(name) == 1 and name.isalpha())):
                raise ValidationFailed(f"{name!r} is not an allowed name (use single-letter variables and functions like sin, sqrt, log)")
            out.append(name)
        elif num is not None:
            out.append(num)
        else:
            out.append("**" if op == "^" else op)
        pos = m.end()
    if not out:
        raise ValidationFailed("empty expression")
    for i, tok in enumerate(out):
        nxt = out[i + 1] if i + 1 < len(out) else None
        nxt2 = out[i + 2] if i + 2 < len(out) else None
        if tok == "**" and nxt and _is_num(nxt) and float(nxt) > MAX_EXPONENT:
            raise ValidationFailed("exponent too large")
        if tok == "**" and nxt == "(" and nxt2 and _is_num(nxt2) and float(nxt2) > MAX_EXPONENT:
            raise ValidationFailed("exponent too large")
        if tok == "factorial" and nxt == "(" and nxt2 and _is_num(nxt2) and float(nxt2) > 1000:
            raise ValidationFailed("factorial argument too large")
    return out


def _is_num(tok: str) -> bool:
    try:
        float(tok)
        return True
    except ValueError:
        return False


def _sympy_namespace() -> dict[str, Any]:
    import sympy as sp

    ns: dict[str, Any] = {name: getattr(sp, name) for name in ("sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh", "sqrt", "cbrt", "log", "exp", "factorial", "floor", "ceiling", "root", "pi", "E", "I", "oo", "Integer", "Float", "Rational", "Symbol")}
    ns["ln"] = sp.log
    ns["abs"] = sp.Abs
    ns["e"] = sp.E
    ns["__builtins__"] = {}
    return ns


def _parse(tokens: list[str]) -> Any:
    import sympy as sp
    from sympy.parsing.sympy_parser import (
        convert_xor,
        implicit_multiplication_application,
        parse_expr,
        standard_transformations,
    )

    text = " ".join(tokens).replace("* *", "**")
    ns = _sympy_namespace()
    try:
        expr = parse_expr(text, local_dict={}, global_dict=ns, transformations=standard_transformations + (implicit_multiplication_application, convert_xor), evaluate=True)
    except Exception as exc:  # noqa: BLE001 - parser errors are user feedback
        raise ValidationFailed(f"could not parse the expression: {exc.__class__.__name__}") from exc
    for p in expr.atoms(sp.Pow):
        if p.exp.is_Number and abs(p.exp) > MAX_EXPONENT:
            raise ValidationFailed("exponent too large")
    return expr


def _fmt(x: Any) -> str:
    import sympy as sp

    try:
        return sp.sstr(x)
    except ValueError as exc:  # e.g. integers beyond the string-conversion limit
        raise ValidationFailed("the result is too large to display") from exc


def _approx(x: Any) -> str | None:
    import sympy as sp

    try:
        v = sp.N(x, 10)
        s = _fmt(v)
        return s if s != _fmt(x) else None
    except (TypeError, ValueError):
        return None


def compute(expression: str, *, task: str = "evaluate", variable: str | None = None) -> MathsResult:
    import sympy as sp

    tokens = tokenise(expression)
    steps: list[str] = []
    if "=" in tokens:
        if tokens.count("=") != 1:
            raise ValidationFailed("use one '=' for an equation")
        i = tokens.index("=")
        lhs, rhs = _parse(tokens[:i]), _parse(tokens[i + 1 :])
        eq = sp.Eq(lhs, rhs)
        parsed = f"{_fmt(lhs)} = {_fmt(rhs)}"
        if task in {"evaluate", "simplify", "explain"}:
            task = "solve"
    else:
        eq = None
        expr = _parse(tokens)
        parsed = _fmt(expr)

    symbols = sorted((eq.free_symbols if eq is not None else expr.free_symbols), key=lambda s: s.name)
    var = sp.Symbol(variable) if variable else (symbols[0] if symbols else None)

    if task == "solve":
        if eq is None:
            eq = sp.Eq(expr, 0)
            steps.append(f"Treating it as {parsed} = 0.")
        if var is None:
            raise ValidationFailed("nothing to solve for: the equation has no variable")
        steps.append(f"Solve for {var}: move everything to one side and find values that make it zero.")
        sols = sp.solve(eq, var)
        if not sols:
            return MathsResult(task, expression, parsed, "no solution found", variable=str(var), steps=steps, explanation=f"No value of {var} satisfies {parsed}.")
        result = ", ".join(_fmt(s) for s in sols)
        approx = ", ".join(a for a in (_approx(s) for s in sols) if a) or None
        expl = f"{var} = {result}" + (f" (about {approx})" if approx else "")
        if len(sols) > 1:
            expl = f"There are {len(sols)} solutions: " + expl
        return MathsResult(task, expression, parsed, result, approx, str(var), steps, expl)
    if task == "simplify":
        out = sp.simplify(expr)
        steps.append("Combine like terms and apply standard identities.")
        return MathsResult(task, expression, parsed, _fmt(out), _approx(out), None, steps, f"{parsed} simplifies to {_fmt(out)}.")
    if task == "differentiate":
        if var is None:
            raise ValidationFailed("differentiate needs a variable")
        out = sp.diff(expr, var)
        steps.append(f"Differentiate term by term with respect to {var}.")
        return MathsResult(task, expression, parsed, _fmt(out), None, str(var), steps, f"d/d{var} of {parsed} is {_fmt(out)}.")
    if task == "integrate":
        if var is None:
            raise ValidationFailed("integrate needs a variable")
        out = sp.integrate(expr, var)
        steps.append(f"Integrate term by term with respect to {var}; add a constant C.")
        return MathsResult(task, expression, parsed, f"{_fmt(out)} + C", None, str(var), steps, f"The integral of {parsed} d{var} is {_fmt(out)} + C.")
    # evaluate / explain
    out = sp.simplify(expr) if symbols else expr
    approx = _approx(out)
    if symbols:
        expl = f"{parsed} has variable{'s' if len(symbols) > 1 else ''} {', '.join(str(s) for s in symbols)}; simplified it is {_fmt(out)}. Give values or ask me to solve an equation."
    else:
        expl = f"{parsed} = {_fmt(out)}" + (f" (about {approx})" if approx else "")
    steps.append("Evaluate using exact arithmetic, then approximate.")
    return MathsResult(task, expression, parsed, _fmt(out), approx, None, steps, expl)
