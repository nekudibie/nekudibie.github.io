"""Pull order events from email search and merge them into the vault's purchases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from companion_vault.structured import PurchaseUpsert

from ..email.base import EmailProvider
from .extract import DEFAULT_QUERIES, extract_order


@dataclass
class SyncReport:
    searched: int = 0
    extracted: int = 0
    created: int = 0
    updated: int = 0
    duplicates: int = 0
    pages: int = 0
    errors: list[str] = field(default_factory=list)


async def sync_orders(email: EmailProvider, vault: Any, *, actor: str, days: int = 90, merchant: str | None = None, max_pages: int = 3, page_size: int = 25) -> SyncReport:
    report = SyncReport()
    seen: set[str] = set()
    for base in DEFAULT_QUERIES:
        query = f"{base} newer_than:{days}d" + (f" {merchant}" if merchant else "")
        token: str | None = None
        for _ in range(max_pages):
            res = await email.search(query, limit=page_size, page_token=token)
            report.pages += 1
            for msg in res.messages:
                if msg.id in seen:
                    continue
                seen.add(msg.id)
                report.searched += 1
                ev = extract_order(msg)
                if ev is None:
                    continue
                report.extracted += 1
                _, outcome = await vault.upsert_purchase(
                    PurchaseUpsert(merchant=ev.merchant, order_ref=ev.order_ref, items=ev.items, amount=ev.amount, currency=ev.currency, ordered_at=ev.event_at if ev.status == "confirmed" else None,
                                   status=ev.status, event_at=ev.event_at, source_message_id=ev.source_message_id),
                    actor=actor,
                )
                setattr(report, outcome if outcome in {"created", "updated"} else "duplicates", getattr(report, outcome if outcome in {"created", "updated"} else "duplicates") + 1)
            token = res.next_page_token
            if not token:
                break
    return report
