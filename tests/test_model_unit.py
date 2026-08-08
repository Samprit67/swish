"""Unit and property tests for the model's building blocks — no HTML, no network."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from swish.data.schema import ContractYear, SeasonLine
from swish.model.aging import cumulative_multiplier, expected_availability, project
from swish.model.params import Params
from swish.model.production import observed_war, true_talent
from swish.model.value import (
    assumed_market_salary,
    star_multiplier,
    surplus_to_pick,
    value_projection,
)

P = Params()


def _season(season_end: int, age: int, *, mp=2200, vorp=3.0, ws=6.0, usg=22.0, games=70) -> SeasonLine:
    return SeasonLine(
        season_end=season_end,
        age=age,
        team="XXX",
        position="SF",
        games=games,
        games_started=games,
        minutes=mp,
        vorp=vorp,
        ws=ws,
        bpm=2.0,
        usg_pct=usg,
        ts_pct=0.58,
        pts=18.0,
        ast=4.0,
        trb=5.0,
        stl=1.0,
        blk=0.5,
    )


# -- production ---------------------------------------------------------


@given(vorp=st.floats(-1, 12), ws=st.floats(-2, 20))
def test_observed_war_is_monotonic_in_its_inputs(vorp, ws):
    lo = observed_war(_season(2026, 25, vorp=vorp, ws=ws), P)[2]
    hi = observed_war(_season(2026, 25, vorp=vorp + 1, ws=ws + 1), P)[2]
    assert hi > lo


def test_more_minutes_means_less_regression():
    big = true_talent([_season(2024, 24), _season(2025, 25), _season(2026, 26, mp=2600, vorp=8)], P)
    small = true_talent([_season(2024, 24), _season(2025, 25), _season(2026, 26, mp=400, vorp=8)], P)
    assert big.war > small.war  # the big-minutes monster season is trusted more


def test_talent_confidence_rises_with_sample():
    thin = true_talent([_season(2026, 25, mp=300)], P)
    thick = true_talent([_season(2024, 23), _season(2025, 24), _season(2026, 25)], P)
    assert thick.confidence > thin.confidence


# -- aging ------------------------------------------------------------


@given(age=st.integers(19, 44))
def test_age_multiplier_declines_after_the_peak(age):
    m_now = cumulative_multiplier(age, age, P)
    m_next = cumulative_multiplier(age, age + 1, P)
    assert m_now == 1.0
    if age >= P.peak_age:
        assert m_next <= m_now


def test_projection_declines_across_the_horizon_for_a_veteran():
    proj = project(6.0, baseline_age=32, first_season_end=2027, recent_games_share=0.8, p=P)
    wars = [y.war for y in proj]
    assert wars == sorted(wars, reverse=True)


@given(age=st.integers(20, 42), share=st.floats(0.2, 1.0))
def test_availability_is_bounded(age, share):
    a = expected_availability(age, share, P)
    assert 0.3 <= a <= 0.97


# -- value ----------------------------------------------------------


@given(war=st.floats(0, 25))
def test_star_multiplier_is_between_one_and_cap(war):
    m = star_multiplier(war, P)
    assert 1.0 <= m <= P.star_premium_cap


def test_higher_salary_means_less_surplus():
    proj = project(7.0, baseline_age=26, first_season_end=2027, recent_games_share=0.9, p=P)
    cheap = value_projection(proj, [ContractYear(2027, 10_000_000)], P, use_contract=True)
    pricey = value_projection(proj, [ContractYear(2027, 45_000_000)], P, use_contract=True)
    assert cheap.surplus_value > pricey.surplus_value
    assert cheap.production_value == pricey.production_value


@given(war=st.floats(-1, 20), t=st.integers(0, 4))
def test_assumed_salary_never_exceeds_the_max(war, t):
    s = assumed_market_salary(war, P, t)
    assert 0.0 <= s <= P.max_salary * (1 + P.cap_growth) ** t


@given(surplus=st.floats(-50e6, 200e6))
def test_pick_number_is_monotonic_in_surplus(surplus):
    lo = surplus_to_pick(surplus, P).pick
    hi = surplus_to_pick(surplus + 5_000_000, P).pick
    assert hi <= lo  # more surplus → earlier (smaller) pick number
