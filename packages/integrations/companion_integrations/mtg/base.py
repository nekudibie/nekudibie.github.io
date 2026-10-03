from __future__ import annotations

from typing import Protocol

from companion_contracts.health import DependencyStatus
from pydantic import BaseModel, ConfigDict, Field

FORMATS = ("standard", "pioneer", "modern", "legacy", "vintage", "commander", "pauper", "brawl", "historic", "alchemy", "explorer", "timeless", "oathbreaker", "penny", "duel", "standardbrawl", "paupercommander", "predh", "oldschool", "premodern", "gladiator", "future")


class Card(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    oracle_id: str | None = None
    scryfall_id: str | None = None
    mana_cost: str | None = None
    cmc: float | None = None
    type_line: str = ""
    oracle_text: str = ""
    colors: list[str] = Field(default_factory=list)
    color_identity: list[str] = Field(default_factory=list)
    legalities: dict[str, str] = Field(default_factory=dict)  # format -> legal | not_legal | banned | restricted
    set_code: str | None = None
    set_name: str | None = None
    scryfall_uri: str | None = None
    fetched_at: str | None = None
    is_custom: bool = False
    is_fixture: bool = False

    @property
    def is_basic_land(self) -> bool:
        return "Basic" in self.type_line and "Land" in self.type_line


class CardLookup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    card: Card | None = None
    ambiguous: list[str] = Field(default_factory=list)
    not_found: bool = False
    from_cache: bool = False
    provider: str
    is_fixture: bool = False


class CardProvider(Protocol):
    name: str
    is_fixture: bool

    async def lookup(self, name: str) -> CardLookup: ...
    async def health(self) -> DependencyStatus: ...
