"""Structured JSON logging with redaction and request correlation.

Design rules (see docs/SECURITY.md):
* one JSON object per line, UTC timestamps;
* a ``request_id`` context variable is attached automatically;
* bearer tokens, ``Authorization`` headers, API keys and configured secret
  values are redacted before they are written;
* private content (message bodies, transcripts, note text) is never logged by
  the application code; this module is the second line of defence, not the first.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
client_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "client_id", default=None
)

_REDACT_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[a-z0-9._\-]+"),
    re.compile(r"(?i)((?:token|secret|password|api[_-]?key|authorization)\"?\s*[:=]\s*\"?)[^\s\",}]+"),
    re.compile(r"(?i)(ya29\.)[a-z0-9._\-]+"),
    re.compile(r"(?i)(sk-)[a-z0-9]{8,}"),
]
_secret_values: set[str] = set()


def register_secret(value: str | None) -> None:
    """Register a literal secret so it is masked wherever it appears in a log line."""
    if value and len(value) >= 6:
        _secret_values.add(value)


def redact(text: str) -> str:
    for pat in _REDACT_PATTERNS:
        text = pat.sub(lambda m: m.group(1) + "[REDACTED]", text)
    for value in _secret_values:
        if value in text:
            text = text.replace(value, "[REDACTED]")
    return text


class JsonFormatter(logging.Formatter):
    RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(tz=UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            payload["request_id"] = rid
        cid = client_id_var.get()
        if cid:
            payload["client_id"] = cid
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        try:
            line = json.dumps(payload, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            line = json.dumps({"ts": payload["ts"], "level": "ERROR", "msg": "unserialisable log record"})
        return redact(line)


class RedactingTextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rid = request_id_var.get()
        prefix = f"[{rid}] " if rid else ""
        base = super().format(record)
        return redact(prefix + base)


def configure_logging(level: str = "INFO", fmt: str = "json", stream: Any = None) -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(stream or sys.stderr)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(RedactingTextFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Quieten chatty libraries; access logs are produced by our own middleware.
    for noisy in ("uvicorn.access", "httpx", "httpcore", "watchfiles"):
        logging.getLogger(noisy).setLevel("WARNING")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
