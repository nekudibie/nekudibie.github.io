"""Heuristic candidate extraction from what the user says.

Explicit "remember ..." requests go through the tool path and become *confirmed* facts.
Everything here is only ever a *candidate* for review, never confirmed automatically, and
each candidate names the message it came from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: list[tuple[re.Pattern[str], str, str | None]] = [
    (re.compile(r"\bmy (?:favourite|favorite|preferred) ([a-z][a-z ]{1,30}?) is ([^.,!?\n]{1,80})", re.I), "favourite {1}", None),
    (re.compile(r"\b[Ii] live in ([A-Z][\w'-]*(?:[ -][A-Z][\w'-]*){0,4})"), "lives in", "{1}"),
    (re.compile(r"\b[Ii] work (?:at|for) ([A-Z][\w&'-]*(?:[ -][A-Z&][\w&'-]*){0,4})"), "works at", "{1}"),
    (re.compile(r"\bmy (name|birthday|timezone|time zone|partner|wife|husband|dog|cat|car|phone) is ([^.,!?\n]{1,60})", re.I), "{1}", None),
    (re.compile(r"\bi prefer ([^.,!?\n]{3,80})", re.I), "preference", "{1}"),
    (re.compile(r"\bi(?:'m| am) allergic to ([^.,!?\n]{2,60})", re.I), "allergy", "{1}"),
    (re.compile(r"\bi usually (?:wake|get) up at ([0-9]{1,2}(?::[0-9]{2})?\s?(?:am|pm)?)", re.I), "usual wake time", "{1}"),
]
_SKIP_PREFIX = re.compile(r"^\s*(remember|note|save|forget)\b", re.I)


@dataclass(frozen=True)
class Candidate:
    subject: str
    predicate: str
    value: str
    quote: str
    confidence: float


def extract_candidates(text: str) -> list[Candidate]:
    if _SKIP_PREFIX.match(text) or len(text) > 2000:
        return []
    out: list[Candidate] = []
    seen: set[tuple[str, str]] = set()
    for pat, pred_tmpl, value_tmpl in _PATTERNS:
        for m in pat.finditer(text):
            groups = m.groups()
            pred = pred_tmpl
            for i, g in enumerate(groups, start=1):
                pred = pred.replace(f"{{{i}}}", g.strip().lower())
            if value_tmpl:
                value = value_tmpl
                for i, g in enumerate(groups, start=1):
                    value = value.replace(f"{{{i}}}", g.strip())
            else:
                value = groups[-1].strip()
            value = value.rstrip(" .")
            if not value or (pred, value.lower()) in seen or len(value) < 2:
                continue
            seen.add((pred, value.lower()))
            start = max(0, m.start() - 40)
            quote = text[start : m.end() + 20].strip()
            out.append(Candidate(subject="owner", predicate=pred, value=value, quote=quote, confidence=0.5))
    return out[:5]
