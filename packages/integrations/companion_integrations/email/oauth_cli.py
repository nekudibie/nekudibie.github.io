"""Loopback OAuth consent for the Gmail read-only scope (run once on the brain host).

Flow: start a one-shot HTTP listener on 127.0.0.1, print the consent URL, receive the
``code`` on the redirect, exchange it with PKCE, store the tokens encrypted. No browser
automation, no password prompt, nothing leaves the machine except the OAuth exchange.
"""

from __future__ import annotations

import asyncio
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .gmail import GmailOAuth, pkce_pair
from .tokens import TokenVault


class _Handler(BaseHTTPRequestHandler):
    result: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        q = parse_qs(urlparse(self.path).query)
        _Handler.result = {k: v[0] for k, v in q.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h2>Companion: Gmail read-only access granted.</h2><p>You can close this tab.</p>" if "code" in q else b"<h2>Consent failed or was denied.</h2>")

    def log_message(self, *_: object) -> None:  # silence the default stderr access log
        return


def login(oauth: GmailOAuth, vault: TokenVault, *, account_label: str, open_browser: bool = True, timeout_s: float = 300) -> dict[str, str]:
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    redirect_uri = f"http://127.0.0.1:{server.server_port}/callback"
    url = oauth.authorization_url(redirect_uri, state, challenge)
    print("Open this address in a browser on this machine (or any machine, then copy the final 127.0.0.1 URL back here if it fails to load):")
    print(url)
    if open_browser:
        webbrowser.open(url)
    done = threading.Event()

    def serve() -> None:
        server.handle_request()
        done.set()

    threading.Thread(target=serve, daemon=True).start()
    if not done.wait(timeout_s):
        server.server_close()
        raise TimeoutError("no consent received within the time limit")
    server.server_close()
    res = _Handler.result
    if res.get("state") != state:
        raise RuntimeError("state mismatch: the redirect did not come from this login attempt")
    if "code" not in res:
        raise RuntimeError(f"consent denied: {res.get('error', 'no code')}")
    tokens = asyncio.run(oauth.exchange_code(res["code"], verifier, redirect_uri))
    if "refresh_token" not in tokens:
        raise RuntimeError("Google did not return a refresh token; remove the app's access at myaccount.google.com/permissions and run login again")
    vault.save(account_label, tokens)
    return {"account": account_label, "scope": tokens.get("scope", ""), "expires_at": str(tokens.get("expires_at"))}


def logout(oauth: GmailOAuth, vault: TokenVault, *, account_label: str) -> bool:
    tok = vault.load(account_label)
    revoked = False
    if tok:
        try:
            revoked = asyncio.run(oauth.revoke(tok.get("refresh_token") or tok.get("access_token", "")))
        finally:
            vault.delete(account_label)
    return revoked
