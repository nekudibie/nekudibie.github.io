"""Deterministic text chunking with stable offset anchors.

Paragraph-aware: paragraphs are packed into chunks of roughly ``chunk_chars``;
a long paragraph is split on sentence/whitespace boundaries with overlap. Anchors
record character offsets into the *original* text so a citation can be re-opened.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PARA_RE = re.compile(r"\n\s*\n")
_BREAK_RE = re.compile(r"(?<=[.!?])\s+|\n")


@dataclass(frozen=True)
class TextChunk:
    seq: int
    text: str
    start: int
    end: int
    paragraph: int


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    pos = 0
    for m in _PARA_RE.finditer(text):
        if m.start() > pos:
            spans.append((pos, m.start()))
        pos = m.end()
    if pos < len(text):
        spans.append((pos, len(text)))
    # trim whitespace inside each span
    out = []
    for s, e in spans:
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if e > s:
            out.append((s, e))
    return out


def _split_long(text: str, start: int, end: int, size: int, overlap: int) -> list[tuple[int, int]]:
    pieces: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        limit = min(cursor + size, end)
        if limit < end:
            window = text[cursor:limit]
            cut = None
            for m in _BREAK_RE.finditer(window):
                if m.start() >= size // 2:
                    cut = m.start()
            if cut is None:
                sp = window.rfind(" ")
                cut = sp if sp >= size // 2 else len(window)
            limit = cursor + cut
            if limit <= cursor:
                limit = min(cursor + size, end)
        pieces.append((cursor, limit))
        if limit >= end:
            break
        cursor = max(limit - overlap, cursor + 1)
    return pieces


def chunk_text(text: str, *, chunk_chars: int = 1200, overlap_chars: int = 150) -> list[TextChunk]:
    if chunk_chars < 100:
        raise ValueError("chunk_chars must be >= 100")
    overlap_chars = max(0, min(overlap_chars, chunk_chars // 3))
    spans = _paragraph_spans(text)
    chunks: list[TextChunk] = []
    buf_start: int | None = None
    buf_end = 0
    buf_para = 0

    def flush() -> None:
        nonlocal buf_start
        if buf_start is not None and buf_end > buf_start:
            chunks.append(
                TextChunk(len(chunks), text[buf_start:buf_end].strip(), buf_start, buf_end, buf_para)
            )
        buf_start = None

    for para_idx, (s, e) in enumerate(spans):
        if e - s > chunk_chars:
            flush()
            for ps, pe in _split_long(text, s, e, chunk_chars, overlap_chars):
                chunks.append(TextChunk(len(chunks), text[ps:pe].strip(), ps, pe, para_idx))
            continue
        if buf_start is None:
            buf_start, buf_end, buf_para = s, e, para_idx
        elif e - buf_start <= chunk_chars:
            buf_end = e
        else:
            flush()
            buf_start, buf_end, buf_para = s, e, para_idx
    flush()
    return [c for c in chunks if c.text]
