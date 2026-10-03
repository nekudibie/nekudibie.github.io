"""Turn an order email into a structured event. Conservative: when a field cannot be read it is
left empty rather than guessed; a confirmation is never treated as a delivery; payment details
are redacted before anything is stored."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from ..email.base import EmailMessage

Status = Literal["confirmed", "shipped", "delivered", "cancelled", "refunded"]

_MERCHANTS = {
    "amazon.": "Amazon", "argos.": "Argos", "ebay.": "eBay", "johnlewis.": "John Lewis", "currys.": "Currys", "screwfix.": "Screwfix", "etsy.": "Etsy",
    "ocado.": "Ocado", "tesco.": "Tesco", "sainsburys.": "Sainsbury's", "apple.": "Apple", "thepihut.": "The Pi Hut", "pimoroni.": "Pimoroni",
}
_REF_PATTERNS = [
    re.compile(r"\b(\d{3}-\d{7}-\d{7})\b"),  # Amazon
    re.compile(r"\border\s*(?:number|no\.?|#|ref(?:erence)?|id)?\s*[:#]?\s*(?=[A-Z0-9-]*\d)([A-Z0-9][A-Z0-9-]{4,24})\b", re.I),  # must contain a digit
]
_STATUS_RULES: list[tuple[Status, re.Pattern[str]]] = [
    ("refunded", re.compile(r"\brefund(?:ed)?\b", re.I)),
    ("cancelled", re.compile(r"\bcancel(?:led|ed)\b", re.I)),
    ("delivered", re.compile(r"\b(?:was|has been|is) delivered\b|\bdelivered:", re.I)),
    ("shipped", re.compile(r"\bdispatched\b|\bshipped\b|\bon its way\b|\bhas been sent\b", re.I)),
    ("confirmed", re.compile(r"\border confirmation\b|\bthanks? for your order\b|\bwe'?ve received your order\b|\byour order\b", re.I)),
]
_AMOUNT_RE = re.compile(r"(?:order total|total|grand total|amount)\s*[:\-]?\s*(£|€|\$|GBP|EUR|USD)\s?(\d+(?:[.,]\d{2})?)", re.I)
_REFUND_AMOUNT_RE = re.compile(r"refund of\s*(£|€|\$)\s?(\d+(?:[.,]\d{2})?)", re.I)
_ITEM_RE = re.compile(r"^\s*(\d+)\s*[x×]\s*(.+?)\s{2,}(?:£|€|\$)\s?(\d+(?:[.,]\d{2})?)\s*$", re.M)
_PAYMENT_RE = re.compile(r"(?:card|visa|mastercard|amex|account)[^\n]{0,30}?(?:ending(?: in)?|\*{2,}|x{2,})\s*\d{4}|\b(?:\d[ -]?){13,19}\b", re.I)
_CURRENCY = {"£": "GBP", "€": "EUR", "$": "USD", "GBP": "GBP", "EUR": "EUR", "USD": "USD"}


@dataclass
class OrderEvent:
    merchant: str
    order_ref: str
    status: Status
    source_message_id: str
    event_at: str | None
    amount: float | None = None
    currency: str | None = None
    items: list[dict[str, object]] = field(default_factory=list)
    link: str | None = None
    subject: str = ""
    confidence: float = 0.5


def redact_payment(text: str) -> str:
    return _PAYMENT_RE.sub("[payment details redacted]", text)


def merchant_of(msg: EmailMessage) -> str | None:
    sender = msg.sender.lower()
    for key, name in _MERCHANTS.items():
        if key in sender:
            return name
    m = re.search(r"@([a-z0-9.-]+)", sender)
    if m:
        domain = m.group(1)
        if any(k in domain for k in ("noreply", "no-reply")):
            return None
        root = domain.split(".")[-2] if domain.count(".") >= 1 else domain
        return root.capitalize() if root not in {"gmail", "outlook", "yahoo", "example"} else None
    return None


def extract_order(msg: EmailMessage) -> OrderEvent | None:
    text = f"{msg.subject}\n{msg.body_text}"
    status: Status | None = None
    for st, pat in _STATUS_RULES:
        if pat.search(msg.subject) or pat.search(msg.body_text[:600]):
            status = st
            break
    if status is None:
        return None
    merchant = merchant_of(msg)
    ref = None
    for pat in _REF_PATTERNS:
        m = pat.search(text)
        if m:
            ref = m.group(1)
            break
    if not merchant or not ref:
        return None
    clean = redact_payment(msg.body_text)
    amount = currency = None
    am = _REFUND_AMOUNT_RE.search(clean) if status == "refunded" else _AMOUNT_RE.search(clean)
    if am:
        currency = _CURRENCY.get(am.group(1).upper() if am.group(1).isalpha() else am.group(1))
        amount = float(am.group(2).replace(",", "."))
    items = [{"quantity": int(q), "name": n.strip(), "price": float(p.replace(",", "."))} for q, n, p in _ITEM_RE.findall(clean)]
    if not items:
        pm = re.search(r"\(([^()]{3,80})\)", clean)
        if pm and status in {"refunded", "cancelled"}:
            items = [{"quantity": 1, "name": pm.group(1).strip(), "price": None}]
    confidence = 0.9 if (amount is not None or items) else 0.6
    return OrderEvent(merchant=merchant, order_ref=ref, status=status, source_message_id=msg.id, event_at=msg.date, amount=amount, currency=currency, items=items,
                      link=msg.link, subject=msg.subject, confidence=confidence)


DEFAULT_QUERIES = ["order confirmation", "your order", "dispatched", "delivered", "refund", "cancelled"]
