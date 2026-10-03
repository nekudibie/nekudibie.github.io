"""A small, clearly labelled card fixture for tests and offline demos.
Legalities below are illustrative fixture data, not a claim about current real-world legality."""

from __future__ import annotations

from companion_contracts.health import DependencyStatus

from .base import Card, CardLookup

_CARDS = {
    "sol ring": Card(name="Sol Ring", type_line="Artifact", mana_cost="{1}", cmc=1, oracle_text="{T}: Add {C}{C}.", color_identity=[], legalities={"commander": "legal", "modern": "not_legal", "vintage": "restricted", "legacy": "banned"}, is_fixture=True),
    "lightning bolt": Card(name="Lightning Bolt", type_line="Instant", mana_cost="{R}", cmc=1, oracle_text="Lightning Bolt deals 3 damage to any target.", colors=["R"], color_identity=["R"], legalities={"commander": "legal", "modern": "legal", "standard": "not_legal", "pauper": "legal"}, is_fixture=True),
    "counterspell": Card(name="Counterspell", type_line="Instant", mana_cost="{U}{U}", cmc=2, oracle_text="Counter target spell.", colors=["U"], color_identity=["U"], legalities={"commander": "legal", "modern": "legal", "pauper": "legal"}, is_fixture=True),
    "thassa, deep-dwelling": Card(name="Thassa, Deep-Dwelling", type_line="Legendary Enchantment Creature — God", mana_cost="{3}{U}", cmc=4, colors=["U"], color_identity=["U"], legalities={"commander": "legal", "pioneer": "legal", "modern": "legal"}, is_fixture=True),
    "island": Card(name="Island", type_line="Basic Land — Island", color_identity=["U"], legalities={"commander": "legal", "modern": "legal", "standard": "legal", "pauper": "legal"}, is_fixture=True),
    "golgari grave-troll": Card(name="Golgari Grave-Troll", type_line="Creature — Skeleton Troll", mana_cost="{4}{G}", cmc=5, colors=["G"], color_identity=["G"], legalities={"commander": "legal", "modern": "banned", "legacy": "legal"}, is_fixture=True),
    "fire // ice": Card(name="Fire // Ice", type_line="Instant // Instant", colors=["R", "U"], color_identity=["R", "U"], legalities={"commander": "legal", "modern": "legal"}, is_fixture=True),
}
_AMBIGUOUS = {"fire": ["Fire // Ice", "Fire Covenant", "Fire Ambush"]}


class FixtureCardProvider:
    name = "fixture"
    is_fixture = True

    async def lookup(self, name: str) -> CardLookup:
        key = name.strip().lower()
        if key in _CARDS:
            return CardLookup(query=name, card=_CARDS[key], provider=self.name, is_fixture=True)
        if key in _AMBIGUOUS:
            return CardLookup(query=name, ambiguous=_AMBIGUOUS[key], provider=self.name, is_fixture=True)
        return CardLookup(query=name, not_found=True, provider=self.name, is_fixture=True)

    async def health(self) -> DependencyStatus:
        return DependencyStatus(name="mtg", status="fixture", detail="fixture card data: seven cards, illustrative legalities")
