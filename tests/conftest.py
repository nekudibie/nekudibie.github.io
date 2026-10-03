from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from companion_api.app import create_app
from companion_core.auth import hash_token
from companion_core.config import AppConfig, ClientConfig, load_config
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
DESK_TOKEN = "desk-test-token-0123456789"
ADMIN_TOKEN = "admin-test-token-0123456789"
ROVER_TOKEN = "rover-test-token-0123456789"
GUEST_TOKEN = "guest-test-token-0123456789"
VAULT_TOKEN = "vault-service-token-0123456789"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


DESK = auth(DESK_TOKEN)
ADMIN = auth(ADMIN_TOKEN)
ROVER = auth(ROVER_TOKEN)
GUEST = auth(GUEST_TOKEN)


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    monkeypatch.setenv("COMPANION_DESK_TOKEN", DESK_TOKEN)
    monkeypatch.setenv("COMPANION_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("COMPANION_VAULT_TOKEN", VAULT_TOKEN)
    monkeypatch.setenv("COMPANION_ENV_FILE", str(tmp_path / "no-such-env"))
    c = load_config(REPO / "config" / "example.yaml")
    c.instance.data_dir = tmp_path / "data"
    c.logging.level = "WARNING"
    c.api.cors_origins = []
    c.worker.embedded = False
    c.clients.append(ClientConfig(id="rover1", role="rover", token_sha256=hash_token(ROVER_TOKEN), memory_scopes=["shared"]))
    c.clients.append(ClientConfig(id="guest1", role="guest", token_sha256=hash_token(GUEST_TOKEN), memory_scopes=[]))
    c.clients.append(
        ClientConfig(id="desk_limited", role="desk", token_sha256=hash_token("limited-desk-token-0123456789"), home_entities=["light.desk_lamp"])
    )
    return c


@pytest.fixture
def make_client(cfg: AppConfig):
    clients: list[TestClient] = []

    def _make(**overrides: Any) -> TestClient:
        app = create_app(cfg, **overrides)
        tc = TestClient(app)
        tc.__enter__()
        clients.append(tc)
        return tc

    yield _make
    for tc in clients:
        tc.__exit__(None, None, None)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def sse(client: TestClient, conversation_id: str, text: str, headers: dict[str, str] = DESK, **body: Any) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    with client.stream("POST", f"/v1/conversations/{conversation_id}/messages", json={"content": text, **body}, headers=headers) as r:
        assert r.status_code == 200, (r.status_code, r.read())
        et = "message"
        for line in r.iter_lines():
            if line.startswith("event:"):
                et = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                events.append((et, json.loads(line.split(":", 1)[1])))
    return events


def text_of(events: list[tuple[str, dict]]) -> str:
    return "".join(d["text"] for t, d in events if t == "token")


def new_conversation(client: TestClient, headers: dict[str, str] = DESK) -> str:
    r = client.post("/v1/conversations", json={}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(autouse=True)
def _no_real_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for k in list(os.environ):
        if k.startswith("COMPANION_") and k not in {"COMPANION_DESK_TOKEN", "COMPANION_ADMIN_TOKEN", "COMPANION_VAULT_TOKEN", "COMPANION_ENV_FILE"}:
            monkeypatch.delenv(k, raising=False)
    yield
