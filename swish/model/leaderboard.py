"""A fast, contract-free value estimate for ranking a whole season at once.

The full model fetches a page per player (career + contract). That's fine for
one lookup but not for 500 of them, so the leaderboard works only from the
season-wide advanced table already in hand: one season of production, run
through the age curve and priced. No surplus, no Monte Carlo — for that, look
the player up individually.
"""

from __future__ import annotations

from dataclasses import dataclass

from swish.data.schema import SeasonContext
from swish.model.aging import cumulative_multiplier
from swish.model.params import Params
from swish.model.value import discount_factor, price_per_win, production_dollars

_SINGLE_SEASON_SHRINK = 3.0  # one season regresses harder than a three-year sample


@dataclass(frozen=True)
class QuickValue:
    pid: str
    name: str
    age: int
    minutes: int
    war: float
    talent: float
    production_value: float


def quick_value(
    pid: str,
    name: str,
    age: int,
    minutes: int,
    vorp: float,
    ws: float,
    usg: float,
    p: Params,
) -> QuickValue:
    war_vorp = vorp * p.vorp_to_wins
    war_ws = ws - p.ws48_replacement * (minutes / 48.0)
    war = p.vorp_weight * war_vorp + (1.0 - p.vorp_weight) * war_ws
    war += p.creation_coef * max(0.0, usg - p.creation_usage_base) * min(1.0, minutes / 2000.0)

    w = minutes / (minutes + p.shrink_minutes * _SINGLE_SEASON_SHRINK)
    talent = w * war + (1.0 - w) * p.talent_prior

    total = 0.0
    for t in range(p.horizon):
        target_age = age + 1 + t
        mult = cumulative_multiplier(age, target_age, p)
        year_war = talent * mult * p.base_availability
        total += production_dollars(year_war, price_per_win(p, t), p) * discount_factor(p, t)

    return QuickValue(pid, name, age, minutes, war, talent, total)


def leaderboard(
    context: SeasonContext, p: Params | None = None, *, min_minutes: int = 500
) -> list[QuickValue]:
    p = p or Params()
    rows = [
        quick_value(
            line.pid,
            line.name,
            line.age,
            line.minutes,
            line.vorp,
            line.ws,
            line.usg_pct,
            p,
        )
        for line in context.lines
        if line.minutes >= min_minutes
    ]
    rows.sort(key=lambda q: q.production_value, reverse=True)
    return rows
