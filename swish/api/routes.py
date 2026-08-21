"""Every HTTP endpoint Swish serves."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import Response

from swish import __version__
from swish.api.deps import get_repo
from swish.api.params import build_params
from swish.api.present import card_dict, career_series, ref_dict, valuation_dict
from swish.data.bref import current_season_end, upcoming_season_end
from swish.data.repo import Repo
from swish.errors import SwishError
from swish.model import evaluate
from swish.model.leaderboard import leaderboard
from swish.model.params import Params

router = APIRouter()

RepoDep = Annotated[Repo, Depends(get_repo)]


# -- meta -----------------------------------------------------------------


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/meta")
def meta() -> dict:
    p = Params()
    return {
        "version": __version__,
        "current_season": current_season_end(),
        "upcoming_season": upcoming_season_end(),
        "defaults": {
            "horizon": p.horizon,
            "discount": p.discount_rate,
            "dollars_per_win_m": p.dollars_per_win / 1_000_000,
        },
    }


# -- players ------------------------------------------------------------


@router.get("/players/search")
def search(repo: RepoDep, q: str = Query(min_length=2)) -> dict:
    return {"query": q, "results": [ref_dict(r) for r in repo.search(q)]}


@router.get("/players/{ident}")
def player(repo: RepoDep, ident: str) -> dict:
    return card_dict(repo.player_card(repo.resolve(ident)))


@router.get("/players/{ident}/headshot")
def headshot(repo: RepoDep, ident: str) -> Response:
    img = repo.headshot(repo.resolve(ident))
    if img is None:
        return Response(status_code=404)
    return Response(
        content=img,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/players/{ident}/value")
def player_value(
    repo: RepoDep,
    ident: str,
    horizon: int | None = None,
    discount: float | None = None,
    dollars_per_win: float | None = None,
    metric: str | None = None,
    use_contract: bool = True,
    season: int | None = None,
) -> dict:
    params = build_params(
        horizon=horizon, discount=discount, dollars_per_win=dollars_per_win, metric=metric
    )
    card = repo.player_card(repo.resolve(ident))
    ctx = repo.season_context(season or current_season_end())
    v = evaluate(card, ctx, params, use_contract=use_contract)
    out = valuation_dict(v, full=True)
    out["career"] = career_series(card, v.params)
    return out


# -- compare ----------------------------------------------------------


@router.get("/compare")
def compare(
    repo: RepoDep,
    ids: str = Query(description="comma-separated names or ids"),
    horizon: int | None = None,
    discount: float | None = None,
    dollars_per_win: float | None = None,
    metric: str | None = None,
    use_contract: bool = True,
) -> dict:
    idents = [s.strip() for s in ids.split(",") if s.strip()][:4]
    if len(idents) < 2:
        raise SwishError("Give at least two players to compare (ids=a,b).")
    params = build_params(
        horizon=horizon, discount=discount, dollars_per_win=dollars_per_win, metric=metric
    )
    ctx = repo.season_context(current_season_end())
    players = []
    for ident in idents:
        v = evaluate(repo.player_card(repo.resolve(ident)), ctx, params, use_contract=use_contract)
        players.append(valuation_dict(v, full=True))
    return {"players": players}


# -- trade ----------------------------------------------------------


@router.post("/trade")
def trade(
    repo: RepoDep,
    body: Annotated[dict, Body()],
) -> dict:
    side_a = [s.strip() for s in body.get("side_a", []) if s.strip()]
    side_b = [s.strip() for s in body.get("side_b", []) if s.strip()]
    if not side_a or not side_b:
        raise SwishError("A trade needs at least one player on each side.")
    opts = body.get("params", {})
    params = build_params(
        horizon=opts.get("horizon"),
        discount=opts.get("discount"),
        dollars_per_win=opts.get("dollars_per_win"),
        metric=opts.get("metric"),
    )
    ctx = repo.season_context(current_season_end())

    def value_side(idents: list[str]) -> list[dict]:
        out = []
        for ident in idents:
            v = evaluate(repo.player_card(repo.resolve(ident)), ctx, params)
            out.append(valuation_dict(v, full=False))
        return out

    a = value_side(side_a)
    b = value_side(side_b)
    sends_a = sum(x["swish_value"] for x in a)  # value Side A trades away
    sends_b = sum(x["swish_value"] for x in b)

    # each side receives what the other sends
    net_a = sends_b - sends_a
    scale = max(abs(sends_a), abs(sends_b), 5_000_000.0)
    if abs(net_a) / scale < 0.12:
        verdict = "roughly fair"
    elif net_a > 0:
        verdict = "Side A wins the trade"
    else:
        verdict = "Side B wins the trade"

    return {
        "side_a": {"players": a, "sends": sends_a, "receives": sends_b, "net": net_a},
        "side_b": {"players": b, "sends": sends_b, "receives": sends_a, "net": -net_a},
        "verdict": verdict,
        "margin": abs(net_a),
    }


# -- leaderboard ----------------------------------------------------


@router.get("/leaderboard")
def leaderboard_route(
    repo: RepoDep,
    season: int | None = None,
    limit: int = 40,
    min_minutes: int = 500,
    horizon: int | None = None,
    discount: float | None = None,
    dollars_per_win: float | None = None,
) -> dict:
    params = build_params(horizon=horizon, discount=discount, dollars_per_win=dollars_per_win)
    season_end = season or current_season_end()
    ctx = repo.season_context(season_end)
    board = leaderboard(ctx, params, min_minutes=min_minutes)[: min(limit, 200)]
    return {
        "season": season_end,
        "note": "on-court production value only — no contract, no simulation",
        "rows": [
            {
                "rank": i + 1,
                "pid": q.pid,
                "name": q.name,
                "age": q.age,
                "minutes": q.minutes,
                "war": round(q.war, 2),
                "talent": round(q.talent, 2),
                "production_value": q.production_value,
            }
            for i, q in enumerate(board)
        ],
    }
