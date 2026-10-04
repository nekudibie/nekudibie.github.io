from __future__ import annotations

import base64
import json

import httpx
import pytest
from companion_core.errors import ConfigError, NotConfigured, UpstreamError
from companion_integrations.email.fixture import FixtureEmailProvider
from companion_integrations.email.gmail import (
    SCOPE,
    GmailOAuth,
    GmailProvider,
    parse_gmail_message,
    pkce_pair,
)
from companion_integrations.email.tokens import TokenVault
from companion_integrations.orders.extract import extract_order, redact_payment
from companion_integrations.orders.sync import sync_orders


def test_token_vault_encrypts_at_rest(tmp_path):
    tv = TokenVault(tmp_path / "tok.enc", "a-long-enough-secret-key")
    tv.save("personal", {"access_token": "ya29.secret", "refresh_token": "1//refresh", "expires_at": 1})
    raw = (tmp_path / "tok.enc").read_bytes()
    assert b"ya29" not in raw and b"refresh" not in raw
    assert tv.load("personal")["refresh_token"] == "1//refresh"
    with pytest.raises(ConfigError):
        TokenVault(tmp_path / "tok.enc", "different-secret-value!").load("personal")
    assert tv.delete("personal") and tv.load("personal") is None
    with pytest.raises(ConfigError):
        TokenVault(tmp_path / "x", "short")


def test_oauth_url_uses_pkce_and_readonly_scope():
    verifier, challenge = pkce_pair()
    url = GmailOAuth("cid", "csecret").authorization_url("http://127.0.0.1:8123/callback", "st4te", challenge)
    assert "gmail.readonly" in url and "code_challenge_method=S256" in url and "access_type=offline" in url and verifier not in url
    assert SCOPE.endswith("gmail.readonly")


@pytest.mark.asyncio
async def test_gmail_provider_refreshes_expired_token_and_pages(tmp_path):
    tv = TokenVault(tmp_path / "tok.enc", "a-long-enough-secret-key")
    tv.save("personal", {"access_token": "old", "refresh_token": "r1", "expires_at": 0})  # already expired
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.host}{request.url.path} {request.headers.get('authorization', '')}")
        if request.url.host == "oauth2.googleapis.com":
            assert b"grant_type=refresh_token" in request.content
            return httpx.Response(200, json={"access_token": "new", "expires_in": 3600})
        if request.headers.get("authorization") != "Bearer new":
            return httpx.Response(401, json={"error": "invalid"})
        if request.url.path.endswith("/messages"):
            page = request.url.params.get("pageToken")
            if page is None:
                return httpx.Response(200, json={"messages": [{"id": "m1"}], "nextPageToken": "p2", "resultSizeEstimate": 2})
            return httpx.Response(200, json={"messages": [{"id": "m2"}]})
        body = base64.urlsafe_b64encode(b"Order #111-2222222-3333333\nOrder total: \xc2\xa312.50\nVisa ending in 1234").decode()
        return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[-1], "threadId": "t", "internalDate": "1760000000000", "snippet": "hi",
                                         "payload": {"mimeType": "multipart/alternative", "headers": [{"name": "From", "value": "Amazon.co.uk <x@amazon.co.uk>"}, {"name": "Subject", "value": "Your Amazon.co.uk order"}],
                                                     "parts": [{"mimeType": "text/plain", "body": {"data": body}}]}})

    transport = httpx.MockTransport(handler)
    p = GmailProvider(GmailOAuth("cid", "cs", transport=transport), tv, transport=transport)
    res = await p.search("order", limit=1)
    assert [m.id for m in res.messages] == ["m1"] and res.next_page_token == "p2"
    res2 = await p.search("order", limit=1, page_token=res.next_page_token)
    assert [m.id for m in res2.messages] == ["m2"] and res2.next_page_token is None
    assert tv.load("personal")["access_token"] == "new"  # refreshed and stored encrypted
    assert sum(1 for c in calls if "oauth2" in c) == 1
    msg = res.messages[0]
    assert msg.sender.startswith("Amazon") and msg.date == "2025-10-09T08:53:20Z" and msg.link.endswith("m1")


@pytest.mark.asyncio
async def test_gmail_not_connected_and_403(tmp_path):
    tv = TokenVault(tmp_path / "tok.enc", "a-long-enough-secret-key")
    p = GmailProvider(GmailOAuth("cid", "cs"), tv)
    with pytest.raises(NotConfigured, match="email-login"):
        await p.search("x")
    tv.save("personal", {"access_token": "a", "refresh_token": "r", "expires_at": 9999999999})
    p = GmailProvider(GmailOAuth("cid", "cs"), tv, transport=httpx.MockTransport(lambda r: httpx.Response(403, json={})))
    with pytest.raises(UpstreamError, match="gmail.readonly"):
        await p.search("x")


def test_parse_gmail_message_falls_back_to_html():
    html_body = base64.urlsafe_b64encode(b"<html><style>x{}</style><p>Thanks for your <b>order</b> &amp; more</p></html>").decode()
    m = parse_gmail_message({"id": "h1", "payload": {"mimeType": "text/html", "body": {"data": html_body}, "headers": []}})
    assert m.body_text == "Thanks for your order & more"


def test_order_extraction_statuses_items_and_redaction():
    fx = FixtureEmailProvider()
    import asyncio

    msgs = {m.id: m for m in asyncio.run(fx.search("", limit=50)).messages}
    conf = extract_order(msgs["fx-amz-1"])
    assert conf.status == "confirmed" and conf.merchant == "Amazon" and conf.order_ref == "203-5567890-1234567" and conf.amount == 39.99 and conf.currency == "GBP"
    assert conf.items == [{"quantity": 1, "name": "Fifine USB Microphone K669", "price": 39.99}]
    assert extract_order(msgs["fx-amz-2"]).status == "shipped"
    assert extract_order(msgs["fx-amz-3"]).status == "delivered"
    ref = extract_order(msgs["fx-amz-4"])
    assert ref.status == "refunded" and ref.amount == 8.49 and ref.items[0]["name"] == "HDMI cable 2m"
    assert extract_order(msgs["fx-amz-5"]).status == "cancelled"
    argos = extract_order(msgs["fx-argos-1"])
    assert argos.merchant == "Argos" and argos.order_ref == "8812-3301" and argos.amount == 29.99
    assert extract_order(msgs["fx-evri-1"]) is None and extract_order(msgs["fx-news-1"]) is None and extract_order(msgs["fx-inject-1"]) is None
    assert "4242" not in redact_payment(msgs["fx-amz-1"].body_text) and "redacted" in redact_payment("Visa ending in 4242")
    assert "redacted" in redact_payment("card 4111 1111 1111 1111")


@pytest.mark.asyncio
async def test_sync_orders_dedupes_and_tracks_status(tmp_path):
    from companion_core.db import Database
    from companion_vault.client import LocalVaultClient
    from companion_vault.service import VaultService

    svc = VaultService(Database(tmp_path / "v.db"))
    svc.migrate()
    vault = LocalVaultClient(svc)
    fx = FixtureEmailProvider(page_size=3)
    rep = await sync_orders(fx, vault, actor="worker", days=365)
    assert rep.pages > 1 and rep.created == 4 and rep.errors == []
    purchases = {p.order_ref: p for p in await vault.list_purchases(scopes=["owner"])}
    assert purchases["203-5567890-1234567"].status == "delivered" and len(purchases["203-5567890-1234567"].status_history) == 3
    assert purchases["203-1190000-7654321"].status == "refunded" and purchases["203-7777777-0000001"].status == "cancelled" and purchases["8812-3301"].status == "confirmed"
    rep2 = await sync_orders(fx, vault, actor="worker", days=365)
    assert rep2.created == 0 and rep2.updated == 0 and rep2.duplicates == rep.extracted
    assert json.dumps(purchases["203-5567890-1234567"].items)  # serialisable


def test_merchant_from_domain_handles_uk_suffixes_and_mailer_subdomains():
    from companion_integrations.orders.extract import merchant_from_domain

    assert merchant_from_domain("mail.overclockers.co.uk") == "Overclockers"
    assert merchant_from_domain("orders.email.whatnot.com") == "Whatnot"
    assert merchant_from_domain("scan.co.uk") == "Scan"
    assert merchant_from_domain("gmail.com") is None and merchant_from_domain("mail.co.uk") is None


def test_status_detection_ignores_footer_policy_text_and_newsletters():
    from companion_integrations.email.base import EmailMessage

    def msg(subject: str, body: str, sender: str = "Acme Parts <orders@mail.acmeparts.co.uk>") -> EmailMessage:
        return EmailMessage(id="m1", thread_id="t", subject=subject, sender=sender, to="n@example.com", date="2026-10-01T10:00:00Z", snippet="", body_text=body)

    footer = "Order number: AB12345\nQuestions? See Returns & Refunds. If you need to cancel, visit your account.\nOrder total: £12.00"
    ev = extract_order(msg("Your order has been dispatched", footer))
    assert ev is not None and ev.status == "shipped" and ev.merchant == "Acmeparts"
    ev2 = extract_order(msg("Thanks for your order", footer))
    assert ev2 is not None and ev2.status == "confirmed"
    assert extract_order(msg("Weekly newsletter", "Mark ordered a market app. order 12345 refund")) is None
    ev3 = extract_order(msg("An update on your purchase", "Your order AB12345 has been refunded. Refund of £12.00 is on its way."))
    assert ev3 is not None and ev3.status == "refunded" and ev3.amount == 12.00
