"""Every constant the model uses, in one place, with where it comes from.

None of these are gospel. They are defensible public-domain estimates, and the
UI lets you move the ones that matter (horizon, discount, $/win). If you think
the aging curve is too harsh, this is the file to argue with.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Params:
    # -- horizon -------------------------------------------------------------
    #: how many future seasons of the player we're valuing
    horizon: int = 3

    # -- production -> wins ------------------------------------------------
    #: Basketball-Reference converts VORP to wins-over-replacement with a factor
    #: of 2.7, but that implies ~26-WAR MVP seasons — well above every published
    #: all-in-one metric (RAPTOR, EPM, LEBRON put peak seasons at 13-18). This
    #: factor is calibrated down so the top of the league lands in that range.
    vorp_to_wins: float = 1.9
    #: replacement level, in Win Shares per 48 minutes. .100 WS/48 is *average*;
    #: a freely-available replacement plays at roughly .055.
    ws48_replacement: float = 0.055
    #: blend of the VORP-based and WS-based wins estimates (rest to WS)
    vorp_weight: float = 0.60
    #: box-score all-in-one metrics underrate high-usage shot creators (the
    #: "creation" literature). A small bump per point of usage above a starter
    #: baseline, scaled by minutes, claws some of that back.
    creation_coef: float = 0.055
    creation_usage_base: float = 24.0

    # -- shrinkage ------------------------------------------------------
    #: minutes at which a season's number gets half weight vs. its prior. Set so
    #: a full healthy season (~2200 min) is ~90% trusted and an injury-shortened
    #: one is pulled harder toward recent form.
    shrink_minutes: float = 260.0
    #: league prior (wins above replacement) used only when a player has no
    #: earlier seasons to regress toward
    talent_prior: float = 0.6
    #: a season is regressed toward the player's own trailing form, blended this
    #: far toward the league prior
    baseline_league_weight: float = 0.15
    #: recent seasons matter more; weight for season t-k is recency_decay**k
    recency_decay: float = 0.5

    # -- age curve -----------------------------------------------------
    #: age at which production peaks
    peak_age: float = 27.0
    #: per-year multiplier deltas relative to peak, by age bucket. A player at
    #: age a gets the product of these from (a+1) forward. Loosely after the
    #: public aging-curve work (Silver 2015; NBA aging-curve replications).
    aging_deltas: dict[int, float] = field(
        default_factory=lambda: {
            19: 0.055,
            20: 0.055,
            21: 0.050,
            22: 0.040,
            23: 0.030,
            24: 0.020,
            25: 0.010,
            26: 0.005,
            27: 0.000,
            28: -0.010,
            29: -0.025,
            30: -0.040,
            31: -0.060,
            32: -0.085,
            33: -0.110,
            34: -0.140,
            35: -0.170,
            36: -0.200,
            37: -0.230,
            38: -0.260,
            39: -0.300,
        }
    )
    aging_delta_old: float = -0.32  # age 40+

    # -- availability ---------------------------------------------------
    #: baseline share of an 82-game season a healthy player is available
    base_availability: float = 0.90
    #: extra games missed per year of age over 30, as a fraction of the season
    availability_age_slope: float = 0.012
    #: how much a player's own recent games-played record counts (rest = base)
    availability_recent_weight: float = 0.5

    # -- dollars ------------------------------------------------------
    #: marginal cost of a win on the open market, USD, at the current cap.
    #: Public estimates cluster around $3.0-3.6M; see docs/METHODOLOGY.md.
    dollars_per_win: float = 3_300_000.0
    #: Wins concentrated on one roster spot are worth more than the same wins
    #: spread across three role players — a contender can't buy a 14-win player
    #: with three 4-win players (roster spots, diminishing returns, the value of
    #: a title). Marginal $/win rises linearly for production above an average
    #: starter, capped. baseline in WAR, slope per WAR, and the ceiling multiple.
    star_premium_baseline: float = 2.0
    star_premium_slope: float = 0.13
    star_premium_cap: float = 2.8
    #: annual salary-cap growth used to inflate future $/win and cap holds
    cap_growth: float = 0.07
    #: a win this season is worth more to a team than a win in three years
    discount_rate: float = 0.08
    #: minimum-salary-ish level; production below this is essentially free talent
    min_salary: float = 3_000_000.0
    #: a maximum salary at the current cap (~35% of a ~$155M cap). Used to cap
    #: the salary a player is assumed to re-sign for once his deal runs out.
    max_salary: float = 55_000_000.0

    # -- draft-pick scale --------------------------------------------
    #: surplus value (USD) attached to each draft slot, anchoring the pick curve.
    #: Fit to a smooth decay through public pick-value charts (Pelton-style):
    #: #1 ~ $55M of surplus, tailing to ~$3M by the end of the second round.
    pick_anchor_value: float = 56_000_000.0
    pick_decay: float = 0.075

    # -- simulation --------------------------------------------------
    n_sims: int = 5000
    #: relative noise on the talent estimate (scaled up for small samples)
    talent_rel_sigma: float = 0.11
    #: extra talent noise for players still on the steep part of the age curve
    youth_sigma_per_year: float = 0.075  # per year under age 25
    #: absolute noise added to each year's age multiplier
    aging_year_sigma: float = 0.03
    #: relative noise on $/win
    dollars_sigma: float = 0.10
    seed: int = 20260831

    def with_(self, **changes: object) -> Params:
        from dataclasses import replace

        return replace(self, **changes)  # type: ignore[arg-type]
