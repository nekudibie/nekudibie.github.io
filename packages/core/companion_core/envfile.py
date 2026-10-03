"""Minimal ``.env`` loader (no third-party dependency).

Rules: ``KEY=value`` per line, ``#`` comments, optional ``export`` prefix, single or
double quotes stripped. Existing process environment variables win, so systemd
``Environment=`` and container env always override the file.
"""

from __future__ import annotations

import os
from pathlib import Path


def parse_env_text(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key:
            result[key] = value
    return result


def load_env_file(path: Path | None, *, override: bool = False) -> list[str]:
    """Load variables from ``path`` into ``os.environ``. Returns the keys that were set."""
    if path is None or not path.is_file():
        return []
    loaded = []
    for key, value in parse_env_text(path.read_text(encoding="utf-8")).items():
        if override or key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded
