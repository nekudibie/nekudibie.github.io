"""Deterministic extraction of decisions and draft actions from transcript segments.

Conservative by design: an owner is only recorded when a name appears in the sentence,
a deadline only when words like "by Friday" appear, and every item carries the quote it
came from. Everything stays a *draft* until the user confirms it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_DUE_RE = re.compile(
    r"\b(?:by|before|due|until)\s+(?:the\s+)?(end of (?:the )?(?:day|week|month)|tomorrow|today|tonight|next week|"
    r"(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?[A-Za-z]{3,9})\b",
    re.I,
)
_VAGUE_RE = re.compile(r"\b(soon|asap|as soon as possible|when you can|at some point|later|eventually)\b", re.I)
_VERBS = r"(?:send|book|write|share|prepare|review|update|check|call|email|draft|finish|set up|look into|follow up|arrange|circulate|fix|test|organise|organize|chase)"
_ACTION_RE = [
    # most specific first: a named person committed to something
    re.compile(r"\b([A-Z][a-z]+)\s+(?:to|will|should|is going to|needs to)\s+(" + _VERBS + r"\b.+)"),
    re.compile(r"\b(?:action|todo|to-do|action item)\s*(?:for\s+([A-Z][a-z]+))?\s*[:\-]\s*(.+)", re.I),
    re.compile(r"\b(?:can|could|would)\s+(?:you|someone)\s+(?:please\s+)?(" + _VERBS + r"\b.+)", re.I),
    re.compile(r"\b(?:I|I'll|I will)\s+(" + _VERBS + r"\b.+)", re.I),
]
_DECISION_RE = re.compile(r"\b(?:we(?:'ve)?\s+(?:decided|agreed)(?:\s+that)?|decision(?:\s+is)?|agreed that|let'?s go with|the plan is)\s*[:\-]?\s*(.+)", re.I)


@dataclass
class DraftAction:
    title: str
    quote: str
    segment_id: str | None
    owner: str | None = None
    owner_confidence: float = 0.0
    due_text: str | None = None
    due_at: str | None = None
    due_confidence: float = 0.0


@dataclass
class DraftDecision:
    statement: str
    quote: str
    segment_id: str | None


@dataclass
class Extraction:
    actions: list[DraftAction] = field(default_factory=list)
    decisions: list[DraftDecision] = field(default_factory=list)
    summary: str = ""


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" .,;:-")


def resolve_due(due_text: str, *, reference: datetime, tz: str = "Europe/London") -> tuple[str | None, float]:
    """Turn 'by Friday' into a date only when it is unambiguous; otherwise keep the words."""
    t = due_text.lower()
    local = reference.astimezone(ZoneInfo(tz)).date()
    if t in {"today", "tonight", "end of the day", "end of day"}:
        return local.isoformat(), 0.7
    if t == "tomorrow":
        return (local + timedelta(days=1)).isoformat(), 0.7
    if t in {"end of the week", "end of week"}:
        return (local + timedelta(days=(4 - local.weekday()) % 7)).isoformat(), 0.5
    if t == "end of the month" or t == "end of month":
        nxt = (local.replace(day=28) + timedelta(days=4)).replace(day=1)
        return (nxt - timedelta(days=1)).isoformat(), 0.5
    m = re.match(r"(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$", t)
    if m:
        target = _WEEKDAYS.index(m.group(2))
        days = (target - local.weekday()) % 7 or 7
        if m.group(1):
            days += 7 if days < 7 else 0
        return (local + timedelta(days=days)).isoformat(), 0.6
    m = re.match(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]{3,9})$", t)
    if m:
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                d = datetime.strptime(f"{m.group(1)} {m.group(2)} {local.year}", fmt).date()
                if d < local - timedelta(days=30):
                    d = d.replace(year=local.year + 1)
                return d.isoformat(), 0.6
            except ValueError:
                continue
    return None, 0.3


def extract(segments: list[tuple[str | None, str]], *, reference: datetime, tz: str = "Europe/London") -> Extraction:
    """``segments`` are (segment_id, text) pairs in order."""
    out = Extraction()
    seen_titles: set[str] = set()
    for seg_id, text in segments:
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            s = sentence.strip()
            if not s:
                continue
            dm = _DECISION_RE.search(s)
            if dm:
                stmt = _clean(dm.group(1))
                if len(stmt) > 3:
                    out.decisions.append(DraftDecision(statement=stmt, quote=s, segment_id=seg_id))
            for pat in _ACTION_RE:
                am = pat.search(s)
                if not am:
                    continue
                groups = am.groups()
                owner = None
                if len(groups) == 2:
                    owner, title = groups[0], groups[1]
                else:
                    title = groups[0]
                title = _clean(re.sub(_DUE_RE, "", title))
                title = re.sub(_VAGUE_RE, "", title).strip(" ,.")
                if len(title) < 4 or title.lower() in seen_titles:
                    break
                seen_titles.add(title.lower())
                action = DraftAction(title=title[0].upper() + title[1:], quote=s, segment_id=seg_id)
                if owner:
                    action.owner, action.owner_confidence = owner, 0.6
                elif re.match(r"\b(?:I|I'll|I will)\b", s):
                    action.owner, action.owner_confidence = None, 0.0  # "I" is whoever was speaking: unknown without diarisation
                due = _DUE_RE.search(s)
                if due:
                    action.due_text = due.group(1)
                    action.due_at, action.due_confidence = resolve_due(due.group(1), reference=reference, tz=tz)
                else:
                    vague = _VAGUE_RE.search(s)
                    if vague:
                        action.due_text, action.due_confidence = vague.group(1), 0.1
                out.actions.append(action)
                break
    total_words = sum(len(t.split()) for _, t in segments)
    first = " ".join(t for _, t in segments[:3])[:300]
    out.summary = (
        f"Automatic outline ({total_words} words transcribed): {len(out.decisions)} decision(s) and {len(out.actions)} draft action(s) found. "
        f"Opening: {first}" if first else "No speech was transcribed."
    )
    return out


def today_in(tz: str) -> date:
    return datetime.now(ZoneInfo(tz)).date()
