"""End-to-end sanity checks: run the whole model on real captured careers and
assert the numbers land in a believable range."""

from __future__ import annotations

import pytest
from swish.model import Params, evaluate
from swish.model.aging import cumulative_multiplier

PIDS = [
    "doncilu01",
    "jokicni01",
    "gilgesh01",
    "wembavi01",
    "banchpa01",
    "thompam01",
    "paulch01",
    "bogdabo01",
]


@pytest.fixture(scope="module")
def valuations(_session_repo):
    repo = _session_repo
    ctx = repo.season_context(2026)
    return {pid: evaluate(repo.player_card(repo.resolve(pid)), ctx) for pid in PIDS}


def test_every_player_produces_a_coherent_valuation(valuations):
    for pid, v in valuations.items():
        assert len(v.projections) == 3, pid
        sim = v.simulation.headline
        assert sim.p10 <= sim.p50 <= sim.p90, pid
        assert -3 < v.talent.war < 22, pid
        assert v.pick.text


def test_reigning_mvps_are_the_most_valuable(valuations):
    jokic = valuations["jokicni01"].headline_value
    sga = valuations["gilgesh01"].headline_value
    for other in ("banchpa01", "paulch01", "bogdabo01", "thompam01"):
        assert jokic > valuations[other].headline_value
        assert sga > valuations[other].headline_value


def test_mvp_center_is_elite_talent(valuations):
    jokic = valuations["jokicni01"]
    assert jokic.talent.war > 11
    scoring = next(p for p in jokic.percentiles if p.key == "pts")
    assert scoring.percentile > 80


def test_cheap_and_productive_beats_expensive_and_average(valuations):
    # Amen Thompson (team option ~$12M) vs Banchero (max ~$42M), similar-ish age
    assert valuations["thompam01"].headline_value > valuations["banchpa01"].headline_value
    assert valuations["thompam01"].used_contract


def test_aging_pulls_the_40_year_old_down(valuations):
    cp3 = valuations["paulch01"]
    wars = [pr.war for pr in cp3.projections]
    assert wars[0] > wars[-1]
    assert cp3.player.name == "Chris Paul"


def test_rookie_scale_projection_is_trimmed(valuations):
    # Wembanyama's B-Ref table projects a max extension; we keep only the real
    # team-option year and assume a market re-signing after it.
    wemby = valuations["wembavi01"]
    assert len(wemby.contract) == 1
    assert wemby.contract[0].salary < 20_000_000
    assert wemby.headline_value > 0  # cheap + very good


def test_contract_toggle_changes_the_headline(repo):
    ctx = repo.season_context(2026)
    card = repo.player_card(repo.resolve("doncilu01"))
    with_deal = evaluate(card, ctx, use_contract=True)
    without = evaluate(card, ctx, use_contract=False)
    assert without.value.headline > with_deal.value.headline
    assert without.value.production_value == pytest.approx(with_deal.value.production_value, rel=1e-9)


def test_shorter_horizon_is_worth_less_for_a_positive_asset(repo):
    ctx = repo.season_context(2026)
    card = repo.player_card(repo.resolve("jokicni01"))
    h3 = evaluate(card, ctx, Params(horizon=3))
    h1 = evaluate(card, ctx, Params(horizon=1))
    assert h3.value.production_value > h1.value.production_value


def test_age_multiplier_is_one_at_the_baseline():
    p = Params()
    assert cumulative_multiplier(27, 27, p) == 1.0
    assert cumulative_multiplier(24, 27, p) > 1.0
    assert cumulative_multiplier(30, 34, p) < 1.0
