"""Step 4-5: age the talent estimate forward and dock it for missed games.

Basketball players don't hold value flat. They improve into their mid-twenties,
plateau, and decline at an accelerating rate through their thirties. The curve
here is a per-year multiplier: to project a 29-year-old two seasons out we
multiply his talent by the age-30 factor, then the age-31 factor.
"""

from __future__ import annotations

from dataclasses import dataclass

from swish.model.params import Params


@dataclass(frozen=True)
class YearProjection:
    season_end: int
    age: int
    age_multiplier: float  # cumulative, relative to the talent baseline
    availability: float  # share of 82 games expected
    war: float  # talent x age_multiplier x availability


def _delta_into(age: int, p: Params) -> float:
    """Fractional change in talent from age ``age-1`` to ``age``."""
    return p.aging_deltas.get(age, p.aging_delta_old)


def cumulative_multiplier(baseline_age: int, target_age: int, p: Params) -> float:
    m = 1.0
    for a in range(baseline_age + 1, target_age + 1):
        m *= 1.0 + _delta_into(a, p)
    for a in range(target_age + 1, baseline_age + 1):  # projecting backwards (rare)
        m /= 1.0 + _delta_into(a, p)
    return m


def expected_availability(age: int, recent_games_share: float | None, p: Params) -> float:
    league = p.base_availability - max(0, age - 30) * p.availability_age_slope
    league = min(0.95, max(0.40, league))
    if recent_games_share is None:
        return league
    w = p.availability_recent_weight
    blended = w * recent_games_share + (1.0 - w) * league
    return min(0.97, max(0.30, blended))


def project(
    talent_war: float,
    *,
    baseline_age: int,
    first_season_end: int,
    recent_games_share: float | None,
    p: Params,
) -> list[YearProjection]:
    out: list[YearProjection] = []
    for t in range(p.horizon):
        season_end = first_season_end + t
        age = baseline_age + 1 + t
        mult = cumulative_multiplier(baseline_age, age, p)
        avail = expected_availability(age, recent_games_share, p)
        out.append(
            YearProjection(
                season_end=season_end,
                age=age,
                age_multiplier=mult,
                availability=avail,
                war=talent_war * mult * avail,
            )
        )
    return out
