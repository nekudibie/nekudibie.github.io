"""Gmail read-only adapter.

OAuth 2.0 for installed apps (docs/SOURCES.md): authorisation at
``https://accounts.google.com/o/oauth2/v2/auth`` with a loopback redirect and PKCE, token
exchange/refresh at ``https://oauth2.googleapis.com/token``, revocation at
``https://oauth2.googleapis.com/revoke``. Scope: ``https://www.googleapis.com/auth/gmail.readonly``
only (a *restricted* scope: an unverified personal OAuth client works for its own test users).
API: ``GET /gmail/v1/users/me/messages`` (``q``, ``maxResults`` <= 500, ``pageToken``) and
``GET /gmail/v1/users/me/messages/{id}?format=full``.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import re
import secrets
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from companion_contracts.health import DependencyStatus
from companion_core.errors import NotConfigured, UpstreamError, UpstreamUnavailable
from companion_core.logging import get_logger

from .base import EmailMessage, EmailSearchResult
from .tokens import TokenVault

log = get_logger(__name__)
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - an endpoint URL, not a secret
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
API_BASE = "https://gmail.googleapis.com"


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class GmailOAuth:
    def __init__(self, client_id: str, client_secret: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=20.0, write=20.0, pool=5.0), transport=transport)

    def authorization_url(self, redirect_uri: str, state: str, code_challenge: str) -> str:
        return AUTH_URL + "?" + urlencode({
            "client_id": self.client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPE, "access_type": "offline",
            "prompt": "consent", "state": state, "code_challenge": code_challenge, "code_challenge_method": "S256",
        })

    async def exchange_code(self, code: str, verifier: str, redirect_uri: str) -> dict[str, Any]:
        r = await self._client.post(TOKEN_URL, data={"client_id": self.client_id, "client_secret": self.client_secret, "code": code, "code_verifier": verifier,
                                                     "grant_type": "authorization_code", "redirect_uri": redirect_uri})
        if r.status_code != 200:
            raise UpstreamError(f"token exchange failed ({r.status_code}): {r.text[:200]}")
        return _with_expiry(r.json())

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        r = await self._client.post(TOKEN_URL, data={"client_id": self.client_id, "client_secret": self.client_secret, "refresh_token": refresh_token, "grant_type": "refresh_token"})
        if r.status_code != 200:
            raise UpstreamError(f"token refresh failed ({r.status_code}): {r.text[:200]}; run `companion-api email-login` again")
        data = _with_expiry(r.json())
        data.setdefault("refresh_token", refresh_token)
        return data

    async def revoke(self, token: str) -> bool:
        r = await self._client.post(REVOKE_URL, data={"token": token})
        return r.status_code == 200

    async def aclose(self) -> None:
        await self._client.aclose()


def _with_expiry(data: dict[str, Any]) -> dict[str, Any]:
    data["expires_at"] = time.time() + float(data.get("expires_in", 3600)) - 60
    return data


class GmailProvider:
    name = "gmail"
    is_fixture = False

    def __init__(self, oauth: GmailOAuth, tokens: TokenVault, *, account_label: str = "personal", transport: httpx.AsyncBaseTransport | None = None, max_retries: int = 3) -> None:
        self.oauth = oauth
        self.tokens = tokens
        self.account_label = account_label
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(base_url=API_BASE, timeout=httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0), transport=transport)
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _access_token(self, *, force_refresh: bool = False) -> str:
        async with self._lock:
            tok = self.tokens.load(self.account_label)
            if not tok or not tok.get("refresh_token"):
                raise NotConfigured("Gmail is not connected: run `uv run companion-api email-login` on the brain host")
            if force_refresh or time.time() >= float(tok.get("expires_at", 0)):
                tok = await self.oauth.refresh(tok["refresh_token"])
                self.tokens.save(self.account_label, tok)
            return str(tok["access_token"])

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        delay = 1.0
        refreshed = False
        for attempt in range(self.max_retries + 1):
            token = await self._access_token()
            try:
                r = await self._client.get(path, params=params, headers={"Authorization": f"Bearer {token}"})
            except httpx.TimeoutException as exc:
                raise UpstreamUnavailable("Gmail API timed out") from exc
            except httpx.TransportError as exc:
                raise UpstreamUnavailable(f"Gmail API unreachable ({exc.__class__.__name__})") from exc
            if r.status_code == 401 and not refreshed:
                refreshed = True
                await self._access_token(force_refresh=True)
                continue
            if r.status_code in {429, 500, 502, 503} and attempt < self.max_retries:
                retry_after = r.headers.get("retry-after")
                await asyncio.sleep(float(retry_after) if retry_after and retry_after.isdigit() else delay)
                delay *= 2
                continue
            if r.status_code == 403:
                raise UpstreamError("Gmail refused the request (403): check the gmail.readonly scope and that your account is a test user of the OAuth client")
            if r.status_code >= 400:
                raise UpstreamError(f"Gmail API returned {r.status_code}: {r.text[:200]}")
            return r.json()
        raise UpstreamUnavailable("Gmail API kept rate-limiting; try again later")

    async def search(self, query: str, *, limit: int = 10, page_token: str | None = None) -> EmailSearchResult:
        params: dict[str, Any] = {"q": query, "maxResults": max(1, min(limit, 100))}
        if page_token:
            params["pageToken"] = page_token
        data = await self._get("/gmail/v1/users/me/messages", params)
        ids = [m["id"] for m in data.get("messages", [])]
        messages = [await self.get(mid) for mid in ids]
        return EmailSearchResult(query=query, messages=messages, next_page_token=data.get("nextPageToken"), result_size_estimate=data.get("resultSizeEstimate"),
                                 provider=self.name, account_label=self.account_label)

    async def get(self, message_id: str) -> EmailMessage:
        data = await self._get(f"/gmail/v1/users/me/messages/{message_id}", {"format": "full"})
        return parse_gmail_message(data)

    async def health(self) -> DependencyStatus:
        tok = self.tokens.load(self.account_label)
        if not tok:
            return DependencyStatus(name="email", status="down", detail="Gmail not connected (companion-api email-login)")
        try:
            data = await self._get("/gmail/v1/users/me/profile")
            return DependencyStatus(name="email", status="ok", detail=f"Gmail connected as {data.get('emailAddress', '?')} (read-only)")
        except (UpstreamError, UpstreamUnavailable, NotConfigured) as exc:
            return DependencyStatus(name="email", status="down", detail=exc.message[:160])


def _b64url(data: str) -> str:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad).decode("utf-8", "replace")


_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)


def _html_to_text(markup: str) -> str:
    text = _TAG_RE.sub(" ", markup)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", "\n", text)).strip()


def _walk_parts(payload: dict[str, Any]) -> tuple[str, str]:
    plain, rich = "", ""
    stack = [payload]
    while stack:
        part = stack.pop(0)
        mime = part.get("mimeType", "")
        body = (part.get("body") or {}).get("data")
        if body and mime == "text/plain":
            plain += _b64url(body)
        elif body and mime == "text/html":
            rich += _b64url(body)
        stack.extend(part.get("parts") or [])
    return plain, rich


def parse_gmail_message(data: dict[str, Any]) -> EmailMessage:
    payload = data.get("payload") or {}
    headers = {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers", [])}
    plain, rich = _walk_parts(payload)
    body = plain.strip() or _html_to_text(rich)
    date = None
    if data.get("internalDate"):
        date = datetime.fromtimestamp(int(data["internalDate"]) / 1000, tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    mid = data.get("id", "")
    return EmailMessage(
        id=mid, thread_id=data.get("threadId"), subject=headers.get("subject", ""), sender=headers.get("from", ""), to=headers.get("to", ""), date=date,
        snippet=html.unescape(data.get("snippet", "")), body_text=body[:20000], labels=data.get("labelIds") or [], link=f"https://mail.google.com/mail/u/0/#all/{mid}" if mid else None,
        provider="gmail",
    )
