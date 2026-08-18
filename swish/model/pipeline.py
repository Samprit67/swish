"""``evaluate`` — the whole model, end to end.

Feed it a :class:`~swish.data.schema.PlayerCard` and the current
:class:`~swish.data.schema.SeasonContext`; get back a :class:`Valuation` with
the headline number, every intermediate quantity behind it, an uncertainty
band, and the caveats a human should know before quoting it.
"""

from __future__ import annotations

from dataclasses import dataclass

from swish.data.bref import upcoming_season_end
from swish.data.schema import ContractYear, PlayerBio, PlayerCard, SeasonContext
from swish.errors import NotEnoughData
from swish.model.aging import YearProjection, project
from swish.model.params import Params
from swish.model.percentiles import Percentile, player_percentiles
from swish.model.production import Talent, true_talent
from swish.model.simulate import SimResult, simulate
from swish.model.value import (
    PickEquivalent,
    ValueBreakdown,
    recent_games_share,
    surplus_to_pick,
    value_projection,
)


@dataclass(frozen=True)
class Valuation:
    player: PlayerBio
    as_of_season: int
    first_projected_season: int
    params: Params
    talent: Talent
    projections: tuple[YearProjection, ...]
    value: ValueBreakdown
    pick: PickEquivalent
    simulation: SimResult
    percentiles: tuple[Percentile, ...]
    contract: tuple[ContractYear, ...]
    used_contract: bool
    notes: tuple[str, ...]

    @property
    def headline_value(self) -> float:
        return self.value.headline

    @property
    def swish_score(self) -> float:
        """Headline surplus in millions, rounded — the number the UI leads with."""
        return round(self.headline_value / 1_000_000, 1)


def evaluate(
    card: PlayerCard,
    context: SeasonContext | None = None,
    params: Params | None = None,
    *,
    use_contract: bool = True,
) -> Valuation:
    p = params or Params()
    seasons = list(card.seasons)
    if not seasons:
        raise NotEnoughData(f"{card.bio.name} has no NBA seasons on record.")

    talent = true_talent(seasons, p)
    last = seasons[-1]
    baseline_age = last.age

    first_season = max(upcoming_season_end(), last.season_end + 1)
    games_share = recent_games_share([s.games for s in seasons[-3:]])

    projections = project(
        talent.war,
        baseline_age=baseline_age,
        first_season_end=first_season,
        recent_games_share=games_share,
        p=p,
    )

    contract = list(card.contract)
    effective_contract = use_contract and bool(contract)

    breakdown: ValueBreakdown = value_projection(projections, contract, p, use_contract=effective_contract)
    pick = surplus_to_pick(breakdown.headline, p)
    sim: SimResult = simulate(talent, projections, contract, p, use_contract=effective_contract)

    pcts: list[Percentile] = []
    if context is not None:
        pcts = player_percentiles(last, context)

    notes = _notes(card, talent, contract, p, use_contract, effective_contract)
    if effective_contract and breakdown.surplus_value < 0 and talent.war > 5.0:
        annual = breakdown.salary_value / max(1, len(breakdown.years))
        notes.insert(
            0,
            f"This is a surplus figure. {card.bio.name} is a good player — his projected "
            f"production is worth {breakdown.production_value / 1e6:.0f}M over the horizon — "
            f"but his salary (~{annual / 1e6:.0f}M/yr) exceeds that. Turn off 'subtract "
            "salary' for on-court value alone.",
        )

    return Valuation(
        player=card.bio,
        as_of_season=last.season_end,
        first_projected_season=first_season,
        params=p,
        talent=talent,
        projections=tuple(projections),
        value=breakdown,
        pick=pick,
        simulation=sim,
        percentiles=tuple(pcts),
        contract=tuple(contract),
        used_contract=effective_contract,
        notes=tuple(notes),
    )


def _notes(
    card: PlayerCard,
    talent: Talent,
    contract: list[ContractYear],
    p: Params,
    requested_contract: bool,
    effective_contract: bool,
) -> list[str]:
    out: list[str] = []
    if talent.confidence < 0.40:
        out.append("Small recent sample — the talent estimate leans heavily on the league prior.")
    if requested_contract and not effective_contract:
        out.append(
            "No guaranteed salary on record (free agent?). Showing on-court production "
            "value, not surplus over a contract."
        )
    for c in contract:
        if c.option:
            from swish.data.schema import OPTION_LABELS

            out.append(f"{c.label} is a {OPTION_LABELS.get(c.option, c.option)}.")
    if card.bio.birth_date is None:
        out.append("No birth date on file — age curve uses the last recorded season's age.")
    if len(talent.seasons) == 1:
        out.append("Only one season of recent data — projection is unusually uncertain.")
    horizon_end = card.seasons[-1].season_end + p.horizon
    guaranteed_through = max((c.season_end for c in contract), default=0)
    if effective_contract and guaranteed_through and guaranteed_through < horizon_end:
        out.append(
            f"Contract is guaranteed only through {guaranteed_through - 1}-"
            f"{str(guaranteed_through)[2:]}; later years assume a market re-signing."
        )
    return out
