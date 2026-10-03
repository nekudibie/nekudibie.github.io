"""Distributed mode: the API talks to the vault over HTTP with a service token."""

from __future__ import annotations

import httpx
from companion_core.db import Database
from companion_vault.app import create_app as create_vault_app
from companion_vault.client import HttpVaultClient
from companion_vault.service import VaultService

from tests.conftest import DESK, ROVER, VAULT_TOKEN, new_conversation, sse, text_of


def test_api_works_against_remote_vault(cfg, make_client, tmp_path):
    cfg.vault.mode = "remote"
    svc = VaultService(Database(tmp_path / "remote-vault.db"))
    svc.migrate()
    vault_app = create_vault_app(cfg, service=svc)
    transport = httpx.ASGITransport(app=vault_app)
    vault_client = HttpVaultClient("http://vault.test", VAULT_TOKEN, transport=transport)
    client = make_client(vault=vault_client)
    assert client.get("/readyz").json()["ready"] is True
    r = client.post("/v1/memory/notes", json={"text": "Remote vault note about the greenhouse heater."}, headers=DESK)
    assert r.status_code == 201
    cid = new_conversation(client)
    assert "[S1]" in text_of(sse(client, cid, "What did I note about the greenhouse?"))
    # scopes are forwarded: the rover (shared only) sees nothing
    assert client.post("/v1/memory/search", json={"query": "greenhouse heater"}, headers=ROVER).json()["hits"] == []
    assert client.get(f"/v1/memory/documents/{r.json()['id']}", headers=ROVER).status_code == 404


def test_vault_service_rejects_wrong_token(cfg, tmp_path):
    from fastapi.testclient import TestClient

    svc = VaultService(Database(tmp_path / "v.db"))
    svc.migrate()
    with TestClient(create_vault_app(cfg, service=svc)) as tc:
        assert tc.get("/v1/vault/stats").status_code == 401
        assert tc.get("/v1/vault/stats", headers={"Authorization": "Bearer nope"}).status_code == 401
        assert tc.get("/v1/vault/stats", headers={"Authorization": f"Bearer {VAULT_TOKEN}"}).status_code == 200
        assert tc.get("/healthz").status_code == 200
