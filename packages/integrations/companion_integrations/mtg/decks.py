"""Decklists, legality rules and the card check.

Legality is decided from the card provider's ``legalities`` plus the deck-construction rules
quoted below (Magic: The Gathering Comprehensive Rules, sections 100.2 and 903.5). Whether a
card is *good* in the deck is opinion and is left to the conversation, clearly separated.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .base import Card, CardProvider

RULES = {
    "100.2a": "In constructed play, each deck has a minimum size of 60 cards and no maximum; a deck may have no more than four of any card with a particular English name, other than basic land cards.",
    "903.5a": "Each Commander deck is subject to a 100-card minimum and maximum deck size, including its commander.",
    "903.5b": "Other than basic lands, each card in a Commander deck must have a different English name.",
    "903.5c": "A card can be included in a Commander deck only if every colour in its colour identity is also found in the colour identity of the deck's commander.",
    "903.3": "Each deck has a legendary creature card designated as its commander.",
}
RULES_SOURCE = "Magic: The Gathering Comprehensive Rules (Wizards of the Coast), sections 100.2 and 903; check the current edition for wording changes."

_LINE_RE = re.compile(r"^\s*(?:(\d+)\s*[xX]?\s+)?(.+?)\s*(?:\(([A-Za-z0-9]{2,5})\)\s*\d*)?\s*$")


class DeckCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    count: int = 1
    section: str = "main"  # main | commander | sideboard
    is_custom: bool = False
    custom_text: str | None = None


class Deck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    format: str
    commander: str | None = None
    cards: list[DeckCard] = Field(default_factory=list)
    notes: str = ""

    @property
    def main_count(self) -> int:
        return sum(c.count for c in self.cards if c.section in {"main", "commander"})

    def find(self, name: str) -> DeckCard | None:
        key = name.strip().lower()
        return next((c for c in self.cards if c.name.lower() == key), None)


def parse_decklist(text: str, *, name: str, format: str, commander: str | None = None) -> Deck:
    """Accepts the common plain-text forms: '4 Lightning Bolt', '1x Sol Ring', set codes in
    brackets, '// Commander' / 'Commander:' / 'Sideboard' section headers, and
    'CUSTOM: Name | rules text' for home-made cards (kept separate and never looked up)."""
    cards: list[DeckCard] = []
    section = "main"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower().rstrip(":")
        if low in {"// commander", "commander", "commanders"}:
            section = "commander"
            continue
        if low in {"// sideboard", "sideboard", "sb"}:
            section = "sideboard"
            continue
        if low in {"// main", "main", "deck", "// deck", "mainboard"}:
            section = "main"
            continue
        if low.startswith("custom:"):
            body = line.split(":", 1)[1]
            cname, _, ctext = body.partition("|")
            cards.append(DeckCard(name=cname.strip(), count=1, section=section, is_custom=True, custom_text=ctext.strip() or None))
            continue
        if line.startswith("//") or line.startswith("#"):
            continue
        if line.lower().startswith("sb:"):
            line = line[3:].strip()
            sec = "sideboard"
        else:
            sec = section
        m = _LINE_RE.match(line)
        if not m:
            continue
        count = int(m.group(1) or 1)
        cname = m.group(2).strip()
        if commander and cname.lower() == commander.lower():
            sec = "commander"
        cards.append(DeckCard(name=cname, count=count, section=sec))
    if commander is None:
        cmd = next((c for c in cards if c.section == "commander"), None)
        commander = cmd.name if cmd else None
    return Deck(name=name, format=format.lower(), commander=commander, cards=cards)


class CheckFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str  # legality | colour_identity | copies | deck_size | custom | unknown
    ok: bool
    detail: str
    rule: str | None = None


class DeckCardCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deck: str
    format: str
    card_query: str
    card: Card | None = None
    ambiguous: list[str] = Field(default_factory=list)
    already_in_deck: int = 0
    findings: list[CheckFinding] = Field(default_factory=list)
    legal: bool | None = None
    rules_source: str = RULES_SOURCE
    provider: str = ""
    is_fixture: bool = False
    data_fetched_at: str | None = None
    note: str = "Legality is a rules question answered here; whether the card suits the deck's plan is a separate judgement."


async def check_card_in_deck(deck: Deck, card_name: str, provider: CardProvider, *, commander_card: Card | None = None) -> DeckCardCheck:
    out = DeckCardCheck(deck=deck.name, format=deck.format, card_query=card_name, provider=provider.name, is_fixture=provider.is_fixture)
    existing = deck.find(card_name)
    if existing and existing.is_custom:
        out.findings.append(CheckFinding(kind="custom", ok=False, detail=f"{existing.name} is a custom card in this deck; it is not legal in sanctioned {deck.format} play and has no official data.", rule=None))
        out.legal = False
        out.already_in_deck = existing.count
        return out
    look = await provider.lookup(card_name)
    out.data_fetched_at = look.card.fetched_at if look.card else None
    if look.ambiguous and look.card is None:
        out.ambiguous = look.ambiguous
        out.findings.append(CheckFinding(kind="unknown", ok=False, detail=f"'{card_name}' matches several cards: {', '.join(look.ambiguous)}. Say which one."))
        return out
    if look.card is None:
        out.findings.append(CheckFinding(kind="unknown", ok=False, detail=f"No card called '{card_name}' was found; check the spelling, or add it as CUSTOM: if it is home-made."))
        return out
    card = look.card
    out.card = card
    out.already_in_deck = existing.count if existing else 0
    status = card.legalities.get(deck.format, "not_legal")
    legal = status in {"legal", "restricted"}
    out.findings.append(CheckFinding(kind="legality", ok=legal, detail=f"{card.name} is {status.replace('_', ' ')} in {deck.format}" + (" (restricted: one copy)" if status == "restricted" else "") + ".", rule=None))
    if deck.format in {"commander", "brawl", "paupercommander", "duel", "predh", "standardbrawl"}:
        if commander_card is not None:
            missing = sorted(set(card.color_identity) - set(commander_card.color_identity))
            ok = not missing
            out.findings.append(CheckFinding(kind="colour_identity", ok=ok, detail=(f"Colour identity {''.join(card.color_identity) or 'colourless'} fits commander {commander_card.name} ({''.join(commander_card.color_identity) or 'colourless'})." if ok else f"Colour identity includes {''.join(missing)}, which {commander_card.name} ({''.join(commander_card.color_identity) or 'colourless'}) does not have."), rule="903.5c"))
            legal = legal and ok
        elif deck.commander:
            out.findings.append(CheckFinding(kind="colour_identity", ok=True, detail=f"Commander {deck.commander} could not be looked up, so colour identity was not checked.", rule="903.5c"))
        if out.already_in_deck >= 1 and not card.is_basic_land:
            out.findings.append(CheckFinding(kind="copies", ok=False, detail=f"The deck already has {card.name}; singleton formats allow one copy of each non-basic card.", rule="903.5b"))
            legal = False
        if deck.main_count >= 100 and not existing:
            out.findings.append(CheckFinding(kind="deck_size", ok=False, detail=f"The deck already has {deck.main_count} cards; adding one means cutting one.", rule="903.5a"))
    else:
        limit = 1 if status == "restricted" else 4
        if not card.is_basic_land and out.already_in_deck >= limit:
            out.findings.append(CheckFinding(kind="copies", ok=False, detail=f"The deck already has {out.already_in_deck} copies; the limit is {limit}.", rule="100.2a"))
            legal = False
        if deck.main_count < 60:
            out.findings.append(CheckFinding(kind="deck_size", ok=True, detail=f"The deck has {deck.main_count} cards; constructed decks need at least 60.", rule="100.2a"))
    out.legal = legal
    return out


def rule_text(rule_id: str) -> str | None:
    return RULES.get(rule_id)


def deck_summary(deck: Deck) -> dict[str, Any]:
    return {"name": deck.name, "format": deck.format, "commander": deck.commander, "main_count": deck.main_count,
            "sideboard_count": sum(c.count for c in deck.cards if c.section == "sideboard"), "custom_cards": [c.name for c in deck.cards if c.is_custom], "unique_cards": len(deck.cards)}
