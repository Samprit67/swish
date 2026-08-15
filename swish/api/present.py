"""Turn model objects into plain JSON-able dicts.

Shared by the API and by ``swish ... --json``. Every number the model computed
is exposed here — the point of the project is that you can follow the whole
chain, not just read the headline.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from swish.data.schema import PlayerCard, PlayerRef
from swish.model import Params
from swish.model.pipeline import Valuation
from swish.model.production import observed_war


def params_dict(p: Params) -> dict[str, Any]:
    return {
        "horizon": p.horizon,
        "discount_rate": p.discount_rate,
        "dollars_per_win": p.dollars_per_win,
        "vorp_weight": p.vorp_weight,
        "cap_growth": p.cap_growth,
    }


def ref_dict(r: PlayerRef) -> dict[str, Any]:
    return {
        "pid": r.pid,
        "name": r.name,
        "position": r.position,
        "from_year": r.from_year,
        "to_year": r.to_year,
    }


def card_dict(card: PlayerCard) -> dict[str, Any]:
    bio = card.bio
    return {
        "pid": bio.pid,
        "name": bio.name,
        "positions": bio.positions,
        "height_in": bio.height_in,
        "weight_lb": bio.weight_lb,
        "birth_date": bio.birth_date.isoformat() if bio.birth_date else None,
        "draft_year": bio.draft_year,
        "draft_pick": bio.draft_pick,
        "team": bio.current_team,
        "seasons": [_season_dict(s) for s in card.seasons],
        "contract": [_contract_dict(c) for c in card.contract],
        "salary_history": [_contract_dict(c) for c in card.salary_history],
    }


def _season_dict(s: Any) -> dict[str, Any]:
    d = asdict(s)
    d["label"] = s.label
    return d


def _contract_dict(c: Any) -> dict[str, Any]:
    return {
        "season_end": c.season_end,
        "label": c.label,
        "salary": c.salary,
        "option": c.option,
        "guaranteed": c.guaranteed,
    }


def valuation_dict(v: Valuation, *, full: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "player": {
            "pid": v.player.pid,
            "name": v.player.name,
            "team": v.player.current_team,
            "positions": v.player.positions,
            "draft_pick": v.player.draft_pick,
        },
        "as_of_season": v.as_of_season,
        "first_projected_season": v.first_projected_season,
        "used_contract": v.used_contract,
        "swish_value": v.headline_value,
        "swish_score": v.swish_score,
        "band": {
            "p10": v.simulation.headline.p10,
            "p50": v.simulation.headline.p50,
            "p90": v.simulation.headline.p90,
        },
        "pick": {
            "number": v.pick.pick,
            "text": v.pick.text,
        },
        "talent_war": v.talent.war,
        "notes": list(v.notes),
    }
    if not full:
        return out

    out["params"] = params_dict(v.params)
    out["talent"] = {
        "war": v.talent.war,
        "observed_war": v.talent.observed_war,
        "confidence": v.talent.confidence,
        "sample_minutes": v.talent.sample_minutes,
        "seasons": [
            {
                "season_end": s.season_end,
                "label": f"{s.season_end - 1}-{str(s.season_end)[2:]}",
                "age": s.age,
                "minutes": s.minutes,
                "war_vorp": s.war_vorp,
                "war_ws": s.war_ws,
                "war_observed": s.war_observed,
                "baseline": s.baseline,
                "war_shrunk": s.war_shrunk,
            }
            for s in v.talent.seasons
        ],
    }
    out["projection"] = [
        {
            "season_end": y.season_end,
            "label": f"{y.season_end - 1}-{str(y.season_end)[2:]}",
            "age": y.age,
            "age_multiplier": y.age_multiplier,
            "availability": y.availability,
            "war": y.war,
        }
        for y in v.projections
    ]
    out["value_years"] = [
        {
            "season_end": yv.season_end,
            "label": f"{yv.season_end - 1}-{str(yv.season_end)[2:]}",
            "war": yv.war,
            "production_value": yv.production_value,
            "salary": yv.salary,
            "salary_option": yv.salary_option,
            "guaranteed": yv.guaranteed,
            "surplus": yv.surplus,
        }
        for yv in v.value.years
    ]
    out["totals"] = {
        "production_value": v.value.production_value,
        "salary_value": v.value.salary_value,
        "surplus_value": v.value.surplus_value,
    }
    out["simulation"] = {
        "headline": _band(v.simulation.headline),
        "production": _band(v.simulation.production),
        "years": [{"season_end": yb.season_end, **_band(yb.war)} for yb in v.simulation.years],
        "histogram": [{"x": x, "d": d} for x, d in v.simulation.histogram],
    }
    out["percentiles"] = [
        {
            "key": pc.key,
            "label": pc.label,
            "value": pc.value,
            "percentile": pc.percentile,
            "league_median": pc.league_median,
        }
        for pc in v.percentiles
    ]
    out["contract"] = [_contract_dict(c) for c in v.contract]
    return out


def _band(b: Any) -> dict[str, float]:
    return {"p10": b.p10, "p50": b.p50, "p90": b.p90, "mean": b.mean}


def career_series(card: PlayerCard, p: Params) -> list[dict[str, Any]]:
    """Full-career WAR and headline box stats, for the trajectory chart."""
    out = []
    for s in card.seasons:
        out.append(
            {
                "season_end": s.season_end,
                "label": s.label,
                "age": s.age,
                "minutes": s.minutes,
                "games": s.games,
                "war": observed_war(s, p)[2],
                "vorp": s.vorp,
                "ws": s.ws,
                "pts": s.pts,
                "ast": s.ast,
                "trb": s.trb,
            }
        )
    return out
