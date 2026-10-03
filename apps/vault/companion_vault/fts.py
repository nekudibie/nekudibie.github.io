"""Build safe FTS5 MATCH expressions from free text."""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[\w'’]+", re.UNICODE)
STOPWORDS = frozenset(
    """a an and are as at be but by did do does for from had has have how i in is it its my of on
    or our that the their there these they this to was we were what when where which who why will
    with you your about any last time me tell find search show remember""".split()
)


def tokens(query: str) -> list[str]:
    raw = [t.strip("'’-").lower() for t in _WORD_RE.findall(query)]
    return [t for t in raw if t]


def keyword_terms(query: str) -> list[str]:
    toks = tokens(query)
    kept = [t for t in toks if t not in STOPWORDS and len(t) > 1]
    return kept or toks


def fts_query(terms: list[str], *, mode: str = "AND", prefix_last: bool = True) -> str:
    if not terms:
        return ""
    quoted = []
    for i, t in enumerate(terms):
        safe = t.replace('"', '""')
        if prefix_last and i == len(terms) - 1 and len(t) >= 3:
            quoted.append(f'"{safe}"*')
        else:
            quoted.append(f'"{safe}"')
    joiner = " AND " if mode == "AND" else " OR "
    return joiner.join(quoted)
