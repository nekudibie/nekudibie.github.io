from __future__ import annotations

from tests.conftest import DESK, GUEST, ROVER, new_conversation, sse, text_of

DECK = "// Commander\n1 Thassa, Deep-Dwelling\n// Main\n1 Counterspell\n30 Island\n"


def test_weather_and_maths_via_chat_and_api(client):
    cid = new_conversation(client)
    events = sse(client, cid, "What's tomorrow's weather?")
    out = text_of(events)
    assert "FIXTURE forecast" in out and "Fetched" in out
    tr = [d for t, d in events if t == "tool_result"][0]
    assert tr["is_fixture"] is True and tr["data"]["attribution"].startswith("fixture")
    out = text_of(sse(client, cid, "solve x^2 - 5x + 6 = 0"))
    assert "x = 2, 3" in out and "SymPy" in out
    out = text_of(sse(client, cid, "what is 17/5 + 2^10?"))
    assert "5137/5" in out
    w = client.get("/v1/weather?day=today", headers=DESK).json()
    assert w["data"]["is_fixture"] and w["data"]["days"]
    m = client.post("/v1/maths", json={"expression": "x^3", "task": "differentiate"}, headers=DESK).json()
    assert m["data"]["result"] == "3*x**2"
    assert client.post("/v1/maths", json={"expression": "__import__('os')"}, headers=DESK).status_code == 422
    assert client.get("/v1/weather", headers=GUEST).status_code == 200  # guests may ask the weather
    assert client.post("/v1/maths", json={"expression": "1+1"}, headers=GUEST).status_code == 200


def test_decks_saved_and_checked_with_rules(client):
    r = client.post("/v1/mtg/decks", json={"name": "Tide Turner", "format": "commander", "decklist": DECK}, headers=DESK)
    assert r.status_code == 201 and r.json()["summary"]["commander"] == "Thassa, Deep-Dwelling" and r.json()["summary"]["main_count"] == 32
    decks = client.get("/v1/mtg/decks", headers=DESK).json()
    assert decks[0]["name"] == "Tide Turner"
    chk = client.post(f"/v1/mtg/decks/{decks[0]['document_id']}/check", json={"card": "Lightning Bolt"}, headers=DESK).json()
    assert chk["data"]["legal"] is False and chk["data"]["rules"]["903.5c"].startswith("A card can be included")
    cid = new_conversation(client)
    out = text_of(sse(client, cid, "Does Lightning Bolt work in my Tide Turner deck?"))
    assert "is not legal" in out and "903.5c" in out and "separate question" in out and "fixture card data" in out
    out = text_of(sse(client, cid, "Does Sol Ring work in my Tide Turner deck?"))
    assert "is legal" in out
    out = text_of(sse(client, cid, "Does Fire work in my Tide Turner deck?"))
    assert "Which card do you mean" in out and "Fire // Ice" in out
    assert client.post("/v1/mtg/decks", json={"name": "x", "format": "nonsense", "decklist": "1 Island"}, headers=DESK).status_code == 422
    assert client.get("/v1/mtg/decks", headers=GUEST).status_code == 403
    # a saved deck is a vault document and searchable
    assert client.post("/v1/memory/search", json={"query": "thassa counterspell", "kinds": ["deck"]}, headers=DESK).json()["hits"]


def test_email_search_orders_and_injection_safety(client):
    cid = new_conversation(client)
    events = sse(client, cid, "Search my emails for kettle")
    out = text_of(events)
    assert "Argos" in out and "[S1]" in out and "fixture mailbox" in out
    srcs = [d for t, d in events if t == "sources"][0]["sources"]
    assert srcs[0]["source_type"] == "email" and srcs[0]["source_uri"].startswith("https://")
    out = text_of(sse(client, cid, "What did I recently buy on Amazon?"))
    assert "Fifine USB Microphone K669" in out and "delivered" in out and "refunded" in out and "not proof of delivery" in out
    orders = client.get("/v1/orders?merchant=amazon&days=365", headers=DESK).json()
    assert {o["order_ref"]: o["status"] for o in orders}["203-5567890-1234567"] == "delivered"
    # payment details never reach the model or the UI
    res = client.post("/v1/email/search", json={"query": "microphone"}, headers=DESK).json()
    assert res["messages"] and "4242" not in res["messages"][0]["body_excerpt"] and "redacted" in res["messages"][0]["body_excerpt"]
    # the injection email is data: the fixture model just reports it, and nothing happens
    events = sse(client, cid, "Search my emails for assistant instructions")
    assert not any(t == "tool_call" and d["name"] == "home_control" for t, d in events)
    assert client.get("/v1/home/entities", headers=DESK).json()[0]["state"] == "off"  # desk lamp untouched
    assert client.post("/v1/email/search", json={"query": "x"}, headers=ROVER).status_code == 403
    st = client.get("/v1/email/status", headers=DESK).json()
    assert st["read_only"] is True and st["is_fixture"] is True


def test_tools_disabled_when_providers_off(cfg, make_client):
    cfg.weather.provider = "disabled"
    cfg.email.provider = "disabled"
    cfg.mtg.provider = "disabled"
    client = make_client()
    tools = {t["name"]: t for t in client.get("/v1/tools", headers=DESK).json()["tools"]}
    assert tools["weather_forecast"]["enabled"] is False and tools["email_search"]["enabled"] is False and tools["deck_card_check"]["enabled"] is False
    assert tools["maths"]["enabled"] is True
    assert client.get("/v1/email/status", headers=DESK).json()["enabled"] is False
    cid = new_conversation(client)
    events = sse(client, cid, "What's tomorrow's weather?")
    assert not any(t == "tool_call" and d["name"] == "weather_forecast" for t, d in events)
    assert "FIXTURE forecast" not in text_of(events) and "°C" not in text_of(events)  # no weather claim without a provider
