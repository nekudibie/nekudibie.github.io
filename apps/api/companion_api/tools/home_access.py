"""Entity allowlisting and friendly-name resolution for home tools and the router."""

from __future__ import annotations

import re
from dataclasses import dataclass

from companion_contracts.home import Entity
from companion_core.auth import ClientIdentity
from companion_core.config import AppConfig
from companion_integrations.home.base import HomeProvider, domain_of


@dataclass
class Resolution:
    entity: Entity | None
    candidates: list[Entity]


def _norm(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"^(the|my)\s+", "", s)
    s = re.sub(r"\s+(lights?|lamp|scene|lighting|mode|camera|cam|feed)$", lambda m: " " + m.group(1), s)
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


class HomeAccess:
    def __init__(self, cfg: AppConfig, provider: HomeProvider | None) -> None:
        self.cfg = cfg
        self.provider = provider

    @property
    def enabled(self) -> bool:
        return self.provider is not None

    def _config_allowed(self, entity_id: str) -> bool:
        assert self.provider is not None
        if domain_of(entity_id) not in self.cfg.home.allowed_domains:
            return False
        if self.provider.is_fixture and not self.cfg.home.allowed_entities:
            return True  # a fixture exposes only its own simulated entities
        return entity_id in self.cfg.home.allowed_entities

    def is_allowed(self, identity: ClientIdentity, entity_id: str) -> bool:
        return self.enabled and self._config_allowed(entity_id) and identity.can_touch_entity(entity_id)

    async def entities(self, identity: ClientIdentity) -> list[Entity]:
        if self.provider is None:
            return []
        return [e for e in await self.provider.list_entities() if self.is_allowed(identity, e.entity_id)]

    async def resolve(self, name: str, identity: ClientIdentity, *, domains: set[str] | None = None) -> Resolution:
        name_n = _norm(name)
        ents = await self.entities(identity)
        if domains:
            ents = [e for e in ents if e.domain in domains]
        by_id = {e.entity_id: e for e in ents}
        # 1. exact entity id
        if name.strip() in by_id:
            return Resolution(by_id[name.strip()], [])
        # 2. configured aliases, scenes and cameras
        for table in (self.cfg.home.aliases, self.cfg.home.scenes, self.cfg.home.cameras):
            for alias, eid in table.items():
                if _norm(alias) == name_n and eid in by_id:
                    return Resolution(by_id[eid], [])
        # 3. friendly name (exact, then without a trailing type word)
        exact = [e for e in ents if _norm(e.friendly_name) == name_n]
        if len(exact) == 1:
            return Resolution(exact[0], [])
        stripped = re.sub(r"\s+(light|lamp|scene|lighting|mode|camera|cam|feed)$", "", name_n)
        loose = [e for e in ents if re.sub(r"\s+(light|lamp|scene|lighting|mode|camera|cam|feed)$", "", _norm(e.friendly_name)) == stripped]
        contains = [e for e in ents if stripped and stripped in _norm(e.friendly_name)]
        # a loose match wins only when nothing else could plausibly be meant
        if len(loose) == 1 and len(contains) <= 1:
            return Resolution(loose[0], [])
        # 4. unique substring match
        if len(contains) == 1:
            return Resolution(contains[0], [])
        return Resolution(None, contains or loose or exact)
