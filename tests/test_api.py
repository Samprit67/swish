"""HTTP-level tests. The app talks to the fixture repo, so still no network."""

from __future__ import annotations


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_meta_reports_the_seasons(client):
    body = client.get("/api/meta").json()
    assert body["current_season"] == 2026
    assert body["upcoming_season"] == 2027
    assert body["defaults"]["horizon"] == 3


def test_search(client):
    body = client.get("/api/players/search", params={"q": "jokic"}).json()
    assert any(row["pid"] == "jokicni01" for row in body["results"])


def test_search_rejects_empty_query(client):
    assert client.get("/api/players/search", params={"q": ""}).status_code == 422


def test_player_card(client):
    body = client.get("/api/players/Luka Doncic").json()
    assert body["pid"] == "doncilu01"
    assert body["draft_pick"] == 3
    assert len(body["seasons"]) >= 7
    assert body["contract"]


def test_value_endpoint_is_complete(client):
    body = client.get("/api/players/jokicni01/value").json()
    assert body["player"]["name"] == "Nikola Jokić"
    assert body["swish_value"] > 0
    assert body["band"]["p10"] <= body["band"]["p50"] <= body["band"]["p90"]
    assert len(body["projection"]) == 3
    assert len(body["value_years"]) == 3
    assert body["percentiles"]
    assert len(body["simulation"]["histogram"]) > 10
    assert body["pick"]["text"]


def test_value_respects_query_params(client):
    base = client.get("/api/players/doncilu01/value").json()
    no_deal = client.get("/api/players/doncilu01/value", params={"use_contract": "false"}).json()
    assert no_deal["swish_value"] > base["swish_value"]

    short = client.get("/api/players/doncilu01/value", params={"horizon": 1}).json()
    assert len(short["projection"]) == 1


def test_headshot_falls_back_to_404_without_an_image(client):
    # the fixture fetcher has no images, so this exercises the graceful miss
    assert client.get("/api/players/jokicni01/headshot").status_code == 404


def test_unknown_player_is_404(client):
    r = client.get("/api/players/Bbbbbq Jjjjjw/value")
    assert r.status_code == 404
    assert "suggestions" in r.json()


def test_compare(client):
    body = client.get("/api/compare", params={"ids": "jokic, banchero, chris paul"}).json()
    assert len(body["players"]) == 3
    names = [p["player"]["name"] for p in body["players"]]
    assert "Nikola Jokić" in names


def test_trade_verdict(client):
    # Side A sends Jokić, receives Banchero + Bogdanović → Side A gets fleeced
    r = client.post(
        "/api/trade",
        json={"side_a": ["jokicni01"], "side_b": ["banchpa01", "bogdabo01"]},
    )
    body = r.json()
    assert body["side_a"]["sends"] > body["side_b"]["sends"]
    assert body["side_a"]["net"] < 0
    assert body["verdict"] == "Side B wins the trade"


def test_leaderboard(client):
    body = client.get("/api/leaderboard", params={"limit": 15}).json()
    assert body["season"] == 2026
    assert len(body["rows"]) == 15
    assert body["rows"][0]["rank"] == 1
    top_names = [r["name"] for r in body["rows"][:5]]
    assert any("Jokić" in n or "Gilgeous" in n for n in top_names)
    values = [r["production_value"] for r in body["rows"]]
    assert values == sorted(values, reverse=True)
