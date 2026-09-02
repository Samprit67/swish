"""Steps 6-8: price the projected wins, subtract the contract, and put the
answer on a scale people argue in — draft picks.

* **Production value** — projected WAR x the market price of a win, with future
  seasons discounted (a win now is worth more than a win in three years) and the
  price of a win grown with the cap.
* **Surplus value** — production value minus what the player is actually owed.
  A guaranteed year past the contract is assumed to be re-signed near market
  value, so it only adds a small "team-control" edge.
* **Pick equivalence** — surplus mapped onto a smooth draft-pick-value curve.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swish.data.schema import ContractYear
from swish.model.aging import YearProjection
from swish.model.params import Params


def assumed_market_salary(war: float, p: Params, years_ahead: int) -> float:
    """What a player of this level re-signs for once his deal runs out.

    The open market pays roughly the base rate per win with no star premium
    (that underpayment of stars is exactly where surplus value comes from), and
    tops out at a maximum salary.
    """
    par = max(0.0, war * p.dollars_per_win)
    ceiling = p.max_salary * (1.0 + p.cap_growth) ** years_ahead
    return min(par, ceiling)


@dataclass(frozen=True)
class YearValue:
    season_end: int
    war: float
    discount_factor: float
    price_per_win: float
    production_value: float  # discounted
    salary: float  # discounted; 0 when contract is ignored
    salary_option: str | None
    guaranteed: bool
    surplus: float  # discounted


@dataclass(frozen=True)
class ValueBreakdown:
    years: tuple[YearValue, ...]
    production_value: float
    salary_value: float
    surplus_value: float
    used_contract: bool

    @property
    def headline(self) -> float:
        return self.surplus_value if self.used_contract else self.production_value


def price_per_win(p: Params, years_ahead: int) -> float:
    return p.dollars_per_win * (1.0 + p.cap_growth) ** years_ahead


def discount_factor(p: Params, years_ahead: int) -> float:
    return 1.0 / (1.0 + p.discount_rate) ** years_ahead


def star_multiplier(war: float, p: Params) -> float:
    """How much more each win is worth when it's concentrated in this one player."""
    over = max(0.0, war - p.star_premium_baseline)
    return min(p.star_premium_cap, 1.0 + p.star_premium_slope * over)


def production_dollars(war: float, price: float, p: Params) -> float:
    return war * price * star_multiplier(war, p)


def value_projection(
    projections: list[YearProjection],
    contract: list[ContractYear],
    p: Params,
    *,
    use_contract: bool,
) -> ValueBreakdown:
    by_year = {c.season_end: c for c in contract}
    years: list[YearValue] = []
    prod_total = salary_total = surplus_total = 0.0

    for t, proj in enumerate(projections):
        disc = discount_factor(p, t)
        ppw = price_per_win(p, t)
        production = production_dollars(proj.war, ppw, p) * disc

        cy = by_year.get(proj.season_end)
        if not use_contract:
            salary = 0.0
            option: str | None = None
            guaranteed = True
            surplus = production
        elif cy is not None:
            salary = cy.salary * disc
            option = cy.option
            guaranteed = cy.guaranteed
            surplus = production - salary
        else:
            # beyond the guaranteed deal — assume a market re-signing
            salary = assumed_market_salary(proj.war, p, t) * disc
            option = "projected"
            guaranteed = False
            surplus = production - salary

        years.append(
            YearValue(
                season_end=proj.season_end,
                war=proj.war,
                discount_factor=disc,
                price_per_win=ppw,
                production_value=production,
                salary=salary,
                salary_option=option,
                guaranteed=guaranteed,
                surplus=surplus,
            )
        )
        prod_total += production
        salary_total += salary
        surplus_total += surplus

    return ValueBreakdown(
        years=tuple(years),
        production_value=prod_total,
        salary_value=salary_total,
        surplus_value=surplus_total,
        used_contract=use_contract,
    )


# --------------------------------------------------------------------------
# draft-pick equivalence
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PickEquivalent:
    value: float  # the surplus dollars being expressed
    pick: float  # fractional pick number (1 = #1 overall); >60 = out of the draft
    text: str  # human phrasing


def pick_value(pick: float, p: Params) -> float:
    return p.pick_anchor_value * math.exp(-p.pick_decay * (max(pick, 1.0) - 1.0))


def surplus_to_pick(surplus: float, p: Params) -> PickEquivalent:
    floor = pick_value(60, p)
    if surplus <= floor:
        return PickEquivalent(surplus, 99.0, _small_phrase(surplus, p))

    if surplus <= pick_value(1, p):
        pick = 1.0 - math.log(surplus / p.pick_anchor_value) / p.pick_decay
        return PickEquivalent(surplus, pick, _pick_phrase(pick))

    # worth more than the #1 pick — express as the #1 pick plus extras
    extra = surplus - pick_value(1, p)
    return PickEquivalent(surplus, 1.0, _premium_phrase(extra, p))


def _pick_phrase(pick: float) -> str:
    n = round(pick)
    if n <= 3:
        return f"a top-3 pick (~#{n})"
    if n <= 5:
        return f"a top-5 pick (~#{n})"
    if n <= 14:
        return f"a lottery pick (~#{n})"
    if n <= 30:
        return f"a first-round pick (~#{n})"
    return "a late-second-round pick"


def _small_phrase(surplus: float, p: Params) -> str:
    if surplus <= 0:
        return "no positive trade value once the contract is subtracted"
    if surplus < p.min_salary:
        return "a second-round pick or cash"
    return "a fringe second-round pick"


def _premium_phrase(extra: float, p: Params) -> str:
    starters = extra / (8.0 * p.dollars_per_win)  # ~8-win surplus per quality young starter
    if starters >= 1.4:
        return f"the #1 pick plus {starters:.0f} quality starters"
    if starters >= 0.6:
        return "the #1 pick plus a young starter"
    return "more than the #1 overall pick"


def recent_games_share(recent_games: list[int]) -> float | None:
    if not recent_games:
        return None
    return min(1.0, sum(recent_games) / (82.0 * len(recent_games)))
