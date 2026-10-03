"""VaultClient: the API's only way to reach the vault.

``LocalVaultClient`` runs the service in-process (one-host mode) and
``HttpVaultClient`` talks to a remote vault host. Both expose the same async
interface so orchestration code never knows where the vault lives.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any, Protocol

import httpx
from companion_contracts.vault import (
    CorrectionRequest,
    DeleteResponse,
    Document,
    DocumentImport,
    NoteCreate,
    SearchRequest,
    SearchResponse,
)
from companion_core.errors import (
    Conflict,
    NotFound,
    UpstreamError,
    UpstreamUnavailable,
    ValidationFailed,
)

from .service import VaultService


class VaultClient(Protocol):
    async def create_note(self, note: NoteCreate, *, actor: str) -> Document: ...
    async def import_document(self, imp: DocumentImport, *, actor: str) -> Document: ...
    async def get_document(self, document_id: str, *, scopes: Iterable[str]) -> Document: ...
    async def list_documents(self, *, scopes: Iterable[str], kinds: list[str] | None = None, limit: int = 50) -> list[Document]: ...
    async def history(self, document_id: str, *, scopes: Iterable[str]) -> list[Document]: ...
    async def search(self, req: SearchRequest, *, scopes: Iterable[str]) -> SearchResponse: ...
    async def correct(self, document_id: str, req: CorrectionRequest, *, actor: str, scopes: Iterable[str]) -> Document: ...
    async def delete(self, document_id: str, *, actor: str, scopes: Iterable[str], reason: str = "") -> DeleteResponse: ...
    async def stats(self) -> dict[str, Any]: ...
    async def health(self) -> dict[str, Any]: ...


class LocalVaultClient:
    def __init__(self, service: VaultService) -> None:
        self.service = service
        self.mode = "embedded"

    async def create_note(self, note: NoteCreate, *, actor: str) -> Document:
        return await asyncio.to_thread(self.service.create_note, note, actor=actor)

    async def import_document(self, imp: DocumentImport, *, actor: str) -> Document:
        return await asyncio.to_thread(self.service.import_document, imp, actor=actor)

    async def get_document(self, document_id: str, *, scopes: Iterable[str]) -> Document:
        return await asyncio.to_thread(self.service.get_document, document_id, scopes=list(scopes))

    async def list_documents(self, *, scopes: Iterable[str], kinds: list[str] | None = None, limit: int = 50) -> list[Document]:
        return await asyncio.to_thread(self.service.list_documents, scopes=list(scopes), kinds=kinds, limit=limit)

    async def history(self, document_id: str, *, scopes: Iterable[str]) -> list[Document]:
        return await asyncio.to_thread(self.service.history, document_id, scopes=list(scopes))

    async def search(self, req: SearchRequest, *, scopes: Iterable[str]) -> SearchResponse:
        return await asyncio.to_thread(self.service.search, req, scopes=list(scopes))

    async def correct(self, document_id: str, req: CorrectionRequest, *, actor: str, scopes: Iterable[str]) -> Document:
        return await asyncio.to_thread(self.service.correct, document_id, req, actor=actor, scopes=list(scopes))

    async def delete(self, document_id: str, *, actor: str, scopes: Iterable[str], reason: str = "") -> DeleteResponse:
        return await asyncio.to_thread(self.service.delete, document_id, actor=actor, scopes=list(scopes), reason=reason)

    async def stats(self) -> dict[str, Any]:
        return await asyncio.to_thread(self.service.stats)

    async def health(self) -> dict[str, Any]:
        ok = await asyncio.to_thread(self.service.db.integrity_ok)
        return {"status": "ok" if ok else "down", "mode": "embedded", "schema": self.service.db.schema_version()}


class HttpVaultClient:
    def __init__(self, base_url: str, token: str, *, timeout_s: float = 10.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.mode = "remote"
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(connect=3.0, read=timeout_s, write=timeout_s, pool=3.0),
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _hdrs(actor: str | None, scopes: Iterable[str] | None) -> dict[str, str]:
        h: dict[str, str] = {}
        if actor:
            h["X-Companion-Actor"] = actor
        if scopes is not None:
            h["X-Companion-Scopes"] = ",".join(scopes)
        return h

    async def _req(self, method: str, path: str, *, actor: str | None = None, scopes: Iterable[str] | None = None, **kw: Any) -> Any:
        try:
            r = await self._client.request(method, path, headers=self._hdrs(actor, scopes), **kw)
        except httpx.TransportError as exc:
            raise UpstreamUnavailable(f"vault unreachable: {exc.__class__.__name__}") from exc
        if r.status_code == 404:
            raise NotFound(_err_msg(r))
        if r.status_code == 409:
            raise Conflict(_err_msg(r))
        if r.status_code == 422:
            raise ValidationFailed(_err_msg(r))
        if r.status_code >= 400:
            raise UpstreamError(f"vault returned {r.status_code}: {_err_msg(r)}")
        return r.json()

    async def create_note(self, note: NoteCreate, *, actor: str) -> Document:
        return Document.model_validate(await self._req("POST", "/v1/vault/notes", actor=actor, json=note.model_dump(mode="json")))

    async def import_document(self, imp: DocumentImport, *, actor: str) -> Document:
        return Document.model_validate(await self._req("POST", "/v1/vault/documents", actor=actor, json=imp.model_dump(mode="json")))

    async def get_document(self, document_id: str, *, scopes: Iterable[str]) -> Document:
        return Document.model_validate(await self._req("GET", f"/v1/vault/documents/{document_id}", scopes=scopes))

    async def list_documents(self, *, scopes: Iterable[str], kinds: list[str] | None = None, limit: int = 50) -> list[Document]:
        params: list[tuple[str, Any]] = [("limit", limit)] + [("kind", k) for k in (kinds or [])]
        data = await self._req("GET", "/v1/vault/documents", scopes=scopes, params=params)
        return [Document.model_validate(d) for d in data]

    async def history(self, document_id: str, *, scopes: Iterable[str]) -> list[Document]:
        data = await self._req("GET", f"/v1/vault/documents/{document_id}/history", scopes=scopes)
        return [Document.model_validate(d) for d in data]

    async def search(self, req: SearchRequest, *, scopes: Iterable[str]) -> SearchResponse:
        return SearchResponse.model_validate(
            await self._req("POST", "/v1/vault/search", scopes=scopes, json=req.model_dump(mode="json"))
        )

    async def correct(self, document_id: str, req: CorrectionRequest, *, actor: str, scopes: Iterable[str]) -> Document:
        return Document.model_validate(
            await self._req("POST", f"/v1/vault/documents/{document_id}/correct", actor=actor, scopes=scopes, json=req.model_dump(mode="json"))
        )

    async def delete(self, document_id: str, *, actor: str, scopes: Iterable[str], reason: str = "") -> DeleteResponse:
        return DeleteResponse.model_validate(
            await self._req("DELETE", f"/v1/vault/documents/{document_id}", actor=actor, scopes=scopes, params={"reason": reason})
        )

    async def stats(self) -> dict[str, Any]:
        return await self._req("GET", "/v1/vault/stats")

    async def health(self) -> dict[str, Any]:
        try:
            r = await self._client.get("/readyz")
            data = r.json()
            return {"status": "ok" if data.get("ready") else "degraded", "mode": "remote", "detail": data}
        except (httpx.HTTPError, ValueError) as exc:
            return {"status": "down", "mode": "remote", "detail": exc.__class__.__name__}


def _err_msg(r: httpx.Response) -> str:
    try:
        data = r.json()
        if isinstance(data, dict):
            if "error" in data and isinstance(data["error"], dict):
                return str(data["error"].get("message", data["error"]))
            if "detail" in data:
                return str(data["detail"])
    except ValueError:
        pass
    return r.text[:200]
