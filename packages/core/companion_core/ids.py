"""Time-sortable identifiers.

Format: ``<prefix>_<26 char Crockford base32 ULID>``. ULIDs sort by creation
time, which keeps SQLite indexes compact and makes logs easy to read. The random
component is 80 bits from ``secrets``.
"""

from __future__ import annotations

import secrets
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(out))


def ulid(now_ms: int | None = None) -> str:
    ts = int(time.time() * 1000) if now_ms is None else now_ms
    rand = secrets.randbits(80)
    return _encode(ts, 10) + _encode(rand, 16)


def new_id(prefix: str) -> str:
    if not prefix.isidentifier():
        raise ValueError(f"id prefix must be an identifier, got {prefix!r}")
    return f"{prefix}_{ulid()}"


def is_id(value: str, prefix: str | None = None) -> bool:
    if "_" not in value:
        return False
    p, _, body = value.rpartition("_")
    if prefix is not None and p != prefix:
        return False
    return len(body) == 26 and all(c in _ALPHABET for c in body)
