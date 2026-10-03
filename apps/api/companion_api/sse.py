"""Server-Sent Events encoding for stream events."""

from __future__ import annotations

from pydantic import BaseModel


def encode(event: BaseModel) -> bytes:
    etype = getattr(event, "type", "message")
    data = event.model_dump_json(exclude_none=True)
    return f"event: {etype}\ndata: {data}\n\n".encode()


def comment(text: str) -> bytes:
    return f": {text}\n\n".encode()


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}
