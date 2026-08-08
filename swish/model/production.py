"""Steps 1-3: turn a career of box-score-derived advanced stats into a single
estimate of the player's current true-talent wins-above-replacement.

The two inputs we trust are **VORP** and **Win Shares**. Both already try to
answer "how many wins was this player worth?", from different directions
(plus-minus vs. box-score credit). We convert each to a wins-above-replacement
number and blend them.

A single season is noisy, so each season is regressed toward the player's own
**trailing form** — the minutes-weighted average of the previous couple of
seasons — not toward a generic replacement level. That way a 22-year-old who
just made a leap isn't dragged back to the league mean, and a veteran coming
off an injury year isn't propped up by what he did five years ago.
"""

from __future__ import annotations

from dataclasses import dataclass

from swish.data.schema import SeasonLine
from swish.errors import NotEnoughData
from swish.model.params import Params

_MINUTES_CAP = 2600.0  # a monster-minutes season shouldn't swamp the blend


@dataclass(frozen=True)
class SeasonWar:
    season_end: int
    age: int
    minutes: int
    games: int
    war_vorp: float
    war_ws: float
    war_observed: float  # blend of the two
    baseline: float  # what this season was regressed toward
    war_shrunk: float  # observed pulled toward the baseline by sample size
    blend_weight: float  # recency x minutes weight this season carries


@dataclass(frozen=True)
class Talent:
    war: float  # true-talent WAR for a full, healthy season
    observed_war: float  # recent blend without shrinkage, for display
    sample_minutes: int
    sample_games: int
    confidence: float  # 0..1 from total minutes seen
    seasons: tuple[SeasonWar, ...]  # the recent seasons that fed the estimate

    @property
    def per_36_war(self) -> float:
        if self.sample_minutes <= 0:
            return 0.0
        return 36.0 * self.observed_war / self.sample_minutes


def observed_war(line: SeasonLine, p: Params) -> tuple[float, float, float]:
    """(vorp-based, ws-based, blended) wins above replacement for one season."""
    war_vorp = line.vorp * p.vorp_to_wins
    war_ws = line.ws - p.ws48_replacement * (line.minutes / 48.0)
    blended = p.vorp_weight * war_vorp + (1.0 - p.vorp_weight) * war_ws
    creation = p.creation_coef * max(0.0, line.usg_pct - p.creation_usage_base)
    blended += creation * min(1.0, line.minutes / 2000.0)
    return war_vorp, war_ws, blended


def _trailing_baseline(prior_seasons: list[tuple[float, SeasonLine]], p: Params) -> float:
    """Minutes-weighted mean of the last <=2 seasons' observed WAR, blended toward
    the league prior. Falls back to the league prior when there's no history."""
    window = prior_seasons[-2:]
    minutes = sum(s.minutes for _, s in window)
    if minutes <= 0:
        return p.talent_prior
    form = sum(o * s.minutes for o, s in window) / minutes
    return (1.0 - p.baseline_league_weight) * form + p.baseline_league_weight * p.talent_prior


def true_talent(seasons: list[SeasonLine], p: Params) -> Talent:
    played = [s for s in seasons if s.minutes > 0]
    if not played:
        raise NotEnoughData(
            "This player has no recent NBA minutes to value. Swish only works for "
            "players with at least part of one NBA season on record."
        )

    obs_by_season = [(observed_war(s, p)[2], s) for s in played]

    recent = played[-3:]
    recent_wars: list[SeasonWar] = []
    k_from_recent = list(range(len(recent) - 1, -1, -1))
    num = den = 0.0
    obs_num = obs_den = 0.0

    for season, k in zip(recent, k_from_recent, strict=True):
        idx = played.index(season)
        baseline = _trailing_baseline(obs_by_season[:idx], p)
        wv, ww, blended = observed_war(season, p)

        w = season.minutes / (season.minutes + p.shrink_minutes)
        shrunk = w * blended + (1.0 - w) * baseline
        weight = (p.recency_decay**k) * min(season.minutes, _MINUTES_CAP)

        recent_wars.append(
            SeasonWar(
                season_end=season.season_end,
                age=season.age,
                minutes=season.minutes,
                games=season.games,
                war_vorp=wv,
                war_ws=ww,
                war_observed=blended,
                baseline=baseline,
                war_shrunk=shrunk,
                blend_weight=weight,
            )
        )
        num += weight * shrunk
        den += weight
        obs_num += weight * blended
        obs_den += weight

    talent = num / den if den else p.talent_prior
    observed = obs_num / obs_den if obs_den else talent
    total_minutes = sum(w.minutes for w in recent_wars)
    total_games = sum(w.games for w in recent_wars)
    confidence = total_minutes / (total_minutes + 3000.0)

    return Talent(
        war=talent,
        observed_war=observed,
        sample_minutes=total_minutes,
        sample_games=total_games,
        confidence=confidence,
        seasons=tuple(recent_wars),
    )


# kept for callers/tests that want a single season's numbers
def season_war(line: SeasonLine, p: Params) -> SeasonWar:
    wv, ww, blended = observed_war(line, p)
    return SeasonWar(
        season_end=line.season_end,
        age=line.age,
        minutes=line.minutes,
        games=line.games,
        war_vorp=wv,
        war_ws=ww,
        war_observed=blended,
        baseline=p.talent_prior,
        war_shrunk=blended,
        blend_weight=0.0,
    )
