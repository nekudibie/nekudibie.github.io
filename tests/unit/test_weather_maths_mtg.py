from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from companion_core.clock import FakeClock
from companion_core.errors import UpstreamUnavailable, ValidationFailed
from companion_integrations.maths.engine import compute, tokenise
from companion_integrations.mtg.decks import check_card_in_deck, parse_decklist
from companion_integrations.mtg.fixture import FixtureCardProvider
from companion_integrations.mtg.scryfall import ScryfallProvider
from companion_integrations.weather.open_meteo import OpenMeteoProvider


# ---------------------------------------------------------------- weather
def _om_payload():
    return {"timezone": "Europe/London", "daily": {"time": ["2026-10-03", "2026-10-04"], "weather_code": [61, 2], "temperature_2m_max": [15.2, 17.0], "temperature_2m_min": [8.1, 9.4],
                                                   "precipitation_sum": [4.2, 0.0], "precipitation_probability_max": [80, 10], "wind_speed_10m_max": [22.0, 15.5]}}


@pytest.mark.asyncio
async def test_open_meteo_parses_caches_and_labels_stale(tmp_path):
    clock = FakeClock(datetime(2026, 10, 3, 8, 0, tzinfo=UTC))
    calls = {"n": 0, "params": None}

    def handler(request):
        calls["n"] += 1
        calls["params"] = dict(request.url.params)
        if calls["n"] >= 2:
            raise httpx.ConnectError("offline")
        return httpx.Response(200, json=_om_payload())

    p = OpenMeteoProvider(53.8, -1.55, location_name="Leeds", cache_path=tmp_path / "w.json", cache_ttl_s=1800, transport=httpx.MockTransport(handler), clock=clock)
    fc = await p.forecast()
    assert calls["params"]["latitude"] == "53.8" and "weather_code" in calls["params"]["daily"] and calls["params"]["timezone"] == "Europe/London"
    assert fc.days[0].description == "slight rain" and fc.days[0].temp_max_c == 15.2 and fc.days[1].precipitation_probability_pct == 10 and not fc.is_stale
    assert "Open-Meteo" in fc.attribution and fc.fetched_at == "2026-10-03T08:00:00.000Z"
    assert (await p.forecast()).is_stale is False and calls["n"] == 1  # served from cache
    clock.advance(hours=2)
    stale = await p.forecast()
    assert stale.is_stale and "120 min ago" in stale.stale_reason and calls["n"] == 2
    fresh = OpenMeteoProvider(53.8, -1.55, cache_path=tmp_path / "none.json", transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("x"))), clock=clock)
    with pytest.raises(UpstreamUnavailable):
        await fresh.forecast()


# ------------------------------------------------------------------ maths
def test_maths_tokeniser_blocks_everything_but_maths():
    assert tokenise("2*x + 3 = 11") == ["2", "*", "x", "+", "3", "=", "11"]
    for bad in ["__import__('os')", "open('x')", "x.__class__", "exec('1')", "a" * 401, "foo(2)", "import os"]:
        with pytest.raises(ValidationFailed):
            tokenise(bad)
    with pytest.raises(ValidationFailed, match="exponent"):
        compute("2^100000")


def test_maths_results_are_symbolic_not_guessed():
    assert compute("2*x + 3 = 11").result == "4"
    r = compute("x^2 - 5x + 6 = 0", task="solve")
    assert r.result == "2, 3" and "2 solutions" in r.explanation
    assert compute("17/5 + 2^10").result == "5137/5" and compute("17/5 + 2^10").approx == "1027.400000"
    assert compute("x^3 + 2x", task="differentiate").result == "3*x**2 + 2"
    assert compute("2x", task="integrate").result == "x**2 + C"
    assert compute("sin(pi/2) + sqrt(16)").result == "5"
    assert compute("(x+1)^2 - (x^2 + 2x + 1)", task="simplify").result == "0"
    with pytest.raises(ValidationFailed):
        compute("1 = 2 = 3")


# -------------------------------------------------------------------- mtg
def test_decklist_parsing_sections_and_custom_cards():
    deck = parse_decklist("// Commander\n1 Thassa, Deep-Dwelling\n// Main\n4x Counterspell (MH2) 267\n30 Island\nSB: 1 Lightning Bolt\nCUSTOM: Neku's Lamp | {T}: Add {U}.\n# comment\n", name="Tide", format="Commander")
    assert deck.commander == "Thassa, Deep-Dwelling" and deck.format == "commander"
    assert [(c.name, c.count, c.section) for c in deck.cards] == [("Thassa, Deep-Dwelling", 1, "commander"), ("Counterspell", 4, "main"), ("Island", 30, "main"), ("Lightning Bolt", 1, "sideboard"), ("Neku's Lamp", 1, "main")]
    assert deck.cards[-1].is_custom and deck.cards[-1].custom_text == "{T}: Add {U}." and deck.main_count == 36


@pytest.mark.asyncio
async def test_legality_separates_rules_from_opinion():
    prov = FixtureCardProvider()
    deck = parse_decklist("1 Thassa, Deep-Dwelling\n1 Counterspell\n30 Island\nCUSTOM: Neku's Lamp | tap for blue", name="Tide", format="commander", commander="Thassa, Deep-Dwelling")
    cmd = (await prov.lookup("Thassa, Deep-Dwelling")).card
    bolt = await check_card_in_deck(deck, "Lightning Bolt", prov, commander_card=cmd)
    assert bolt.legal is False and any(f.kind == "colour_identity" and f.rule == "903.5c" and not f.ok for f in bolt.findings)
    ring = await check_card_in_deck(deck, "Sol Ring", prov, commander_card=cmd)
    assert ring.legal is True and "separate judgement" in ring.note
    dup = await check_card_in_deck(deck, "Counterspell", prov, commander_card=cmd)
    assert dup.legal is False and any(f.rule == "903.5b" for f in dup.findings)
    island = await check_card_in_deck(deck, "Island", prov, commander_card=cmd)
    assert island.legal is True  # basic lands escape the singleton rule
    amb = await check_card_in_deck(deck, "Fire", prov, commander_card=cmd)
    assert amb.legal is None and amb.ambiguous == ["Fire // Ice", "Fire Covenant", "Fire Ambush"]
    custom = await check_card_in_deck(deck, "Neku's Lamp", prov, commander_card=cmd)
    assert custom.legal is False and custom.findings[0].kind == "custom"
    modern = parse_decklist("4 Lightning Bolt\n4 Golgari Grave-Troll\n20 Island", name="M", format="modern")
    troll = await check_card_in_deck(modern, "Golgari Grave-Troll", prov)
    assert troll.legal is False and "banned" in troll.findings[0].detail
    fifth = await check_card_in_deck(modern, "Lightning Bolt", prov)
    assert fifth.legal is False and any(f.rule == "100.2a" and f.kind == "copies" for f in fifth.findings)


@pytest.mark.asyncio
async def test_scryfall_adapter_headers_pacing_cache_and_fuzzy(tmp_path):
    seen = []

    def handler(request):
        seen.append((request.url.path, dict(request.url.params), request.headers.get("user-agent"), request.headers.get("accept")))
        name = request.url.params.get("exact") or request.url.params.get("fuzzy")
        if name == "Sol Ring":
            return httpx.Response(200, json={"name": "Sol Ring", "id": "x", "oracle_id": "o", "type_line": "Artifact", "color_identity": [], "legalities": {"commander": "legal"}, "set": "c21", "scryfall_uri": "https://scryfall.com/card/x"})
        if request.url.params.get("exact") == "sol rng":
            return httpx.Response(404, json={"object": "error", "code": "not_found"})
        if request.url.params.get("fuzzy") == "sol rng":
            return httpx.Response(200, json={"name": "Sol Ring", "legalities": {}})
        if request.url.params.get("fuzzy") == "fire":
            return httpx.Response(404, json={"object": "error", "details": "Too many cards match ambiguous name “fire”. Add more words to refine your search: Fire // Ice, Fire Ambush"})
        return httpx.Response(404, json={"object": "error", "code": "not_found", "details": "No cards found"})

    clock = FakeClock(datetime(2026, 10, 3, tzinfo=UTC))
    p = ScryfallProvider(tmp_path / "cache", user_agent="TestApp/1.0", transport=httpx.MockTransport(handler), clock=clock, min_interval_s=0)
    r = await p.lookup("Sol Ring")
    assert r.card.name == "Sol Ring" and seen[0][2] == "TestApp/1.0" and "application/json" in seen[0][3]
    r2 = await p.lookup("Sol Ring")
    assert r2.from_cache and len(seen) == 1  # 24 h cache honoured
    fuzzy = await p.lookup("sol rng")
    assert fuzzy.card is None and fuzzy.ambiguous == ["Sol Ring"]  # a different name is offered, not silently substituted
    amb = await p.lookup("fire")
    assert amb.ambiguous == ["Fire // Ice", "Fire Ambush"] and not amb.not_found
    assert (await p.lookup("zzz")).not_found
