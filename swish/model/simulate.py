"""Step 9: how wrong could this be?

The point estimate hides a lot of guessing — about the player's true level, how
he ages, whether he stays healthy, and what a win costs. We resample all four a
few thousand times and report the 10th / 50th / 90th percentile of the result,
plus a per-season band for the projection fan chart.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from swish.data.schema import ContractYear
from swish.model.aging import YearProjection
from swish.model.params import Params
from swish.model.production import Talent
from swish.model.value import discount_factor, price_per_win


@dataclass(frozen=True)
class Band:
    p10: float
    p50: float
    p90: float
    mean: float


@dataclass(frozen=True)
class YearBand:
    season_end: int
    war: Band


@dataclass(frozen=True)
class SimResult:
    headline: Band  # surplus value, or production value when contract is ignored
    production: Band
    years: tuple[YearBand, ...]
    histogram: tuple[tuple[float, float], ...]  # (bin_center, density)


def _band(samples: np.ndarray) -> Band:
    p10, p50, p90 = np.percentile(samples, [10, 50, 90])
    return Band(float(p10), float(p50), float(p90), float(samples.mean()))


def simulate(
    talent: Talent,
    projections: list[YearProjection],
    contract: list[ContractYear],
    p: Params,
    *,
    use_contract: bool,
) -> SimResult:
    rng = np.random.default_rng(p.seed)
    n = p.n_sims
    horizon = len(projections)

    # 1. true talent — noisier when we've seen fewer minutes, and noisier still
    #    for young players who are still moving fast along the age curve
    rel_sigma = p.talent_rel_sigma / max(talent.confidence, 0.25)
    baseline_age = projections[0].age - 1 if projections else 27
    youth = max(0, 25 - baseline_age) * p.youth_sigma_per_year
    talent_sigma = abs(talent.war) * (rel_sigma + youth) + 0.35
    talent_draw = rng.normal(talent.war, talent_sigma, n)

    # 2. aging — a compounding per-year wobble on top of the curve
    aging_steps = rng.normal(1.0, p.aging_year_sigma, (n, horizon))
    aging_cum = np.cumprod(aging_steps, axis=1)

    # 3. availability wobble, and 4. price of a win
    avail_noise = np.clip(rng.normal(1.0, 0.06, (n, horizon)), 0.7, 1.2)
    price_noise = rng.normal(1.0, p.dollars_sigma, (n, horizon))

    contract_by_year = {c.season_end: c for c in contract}
    war_years = np.zeros((n, horizon))
    production_total = np.zeros(n)
    headline_total = np.zeros(n)

    for t, proj in enumerate(projections):
        ratio = proj.age_multiplier * proj.availability  # deterministic part
        war_t = talent_draw * ratio * aging_cum[:, t] * avail_noise[:, t]
        war_years[:, t] = war_t

        disc = discount_factor(p, t)
        ppw = price_per_win(p, t) * price_noise[:, t]
        star_mult = np.minimum(
            p.star_premium_cap,
            1.0 + p.star_premium_slope * np.maximum(0.0, war_t - p.star_premium_baseline),
        )
        production_t = war_t * ppw * star_mult * disc
        production_total += production_t

        cy = contract_by_year.get(proj.season_end)
        if not use_contract:
            headline_total += production_t
        elif cy is not None:
            headline_total += production_t - cy.salary * disc
        else:
            # projected market re-signing, per simulated WAR that year
            par = np.maximum(p.min_salary, war_t * p.dollars_per_win)
            resign = np.minimum(par, p.max_salary * (1.0 + p.cap_growth) ** t)
            headline_total += production_t - resign * disc

    counts, edges = np.histogram(headline_total, bins=32, density=True)
    centers = 0.5 * (edges[:-1] + edges[1:])

    return SimResult(
        headline=_band(headline_total),
        production=_band(production_total),
        years=tuple(
            YearBand(season_end=projections[t].season_end, war=_band(war_years[:, t]))
            for t in range(horizon)
        ),
        histogram=tuple((float(c), float(d)) for c, d in zip(centers, counts, strict=True)),
    )
