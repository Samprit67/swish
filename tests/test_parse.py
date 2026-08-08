"""Parser tests against real captured Basketball-Reference HTML."""

from __future__ import annotations

import datetime as dt

import pytest
from swish.data import parse
from swish.data.bref import current_season_end

from conftest import load_fixture


@pytest.fixture
def luka_html() -> str:
    return load_fixture("player_doncilu01.html.gz")


def test_bio_pulls_the_key_facts(luka_html: str) -> None:
    bio = parse.parse_bio(luka_html, "doncilu01")
    assert bio.name == "Luka Dončić"
    assert bio.birth_date == dt.date(1999, 2, 28)
    assert bio.draft_pick == 3
    assert bio.draft_year == 2018
    assert bio.height_in == 6 * 12 + 8
    assert "Los Angeles Lakers" in (bio.current_team or "")
    assert 26 < bio.age_on(dt.date(2025, 10, 1)) < 27


def test_seasons_are_nba_regular_season_one_row_each(luka_html: str) -> None:
    seasons = parse.parse_seasons(luka_html)
    years = [s.season_end for s in seasons]
    assert years == sorted(years)
    assert len(years) == len(set(years)), "traded seasons must collapse to one row"
    assert years[0] == 2019

    latest = seasons[-1]
    assert latest.season_end == 2026
    assert latest.minutes > 2000
    assert latest.vorp > 4  # 2025-26 bounce-back
    assert latest.pts > 25


def test_traded_season_uses_the_combined_row(luka_html: str) -> None:
    # 2024-25 Luka played for DAL then LAL; the combined row has the most minutes.
    s = {x.season_end: x for x in parse.parse_seasons(luka_html)}[2025]
    assert s.minutes > 1700
    assert s.team in {"2TM", "TOT"}


def test_contract_is_future_guaranteed_money(luka_html: str) -> None:
    years = parse.parse_contract(luka_html, from_season_end=2027)
    assert years, "Luka has a known contract"
    assert all(c.season_end >= 2027 for c in years)
    assert all(c.salary > 20_000_000 for c in years)
    assert years == sorted(years, key=lambda c: c.season_end)


def test_salary_history_goes_back_to_rookie_year(luka_html: str) -> None:
    hist = parse.parse_salary_history(luka_html)
    assert hist[0].season_end == 2019
    assert 5_000_000 < hist[0].salary < 10_000_000


def test_letter_index_resolves_ids() -> None:
    refs = parse.parse_index(load_fixture("index_d.html.gz"))
    by_pid = {r.pid: r for r in refs}
    assert "doncilu01" in by_pid
    luka = by_pid["doncilu01"]
    assert luka.name == "Luka Dončić"
    assert luka.to_year >= 2025


def test_season_context_has_the_league() -> None:
    ctx = parse.parse_season_context(
        load_fixture("season_2026_advanced.html.gz"),
        load_fixture("season_2026_per_game.html.gz"),
        2026,
    )
    assert ctx.season_end == 2026
    assert len(ctx.lines) > 400
    jokic = next(line for line in ctx.lines if line.pid == "jokicni01")
    assert jokic.vorp > 5
    assert jokic.pts > 20
    assert len(ctx.qualified(min_minutes=1000)) > 150


def test_season_end_parsing() -> None:
    assert parse._season_end("2025-26") == 2026
    assert parse._season_end("1999-00") == 2000
    assert parse._season_end("2024") == 2024
    assert parse._season_end("junk") is None


def test_current_season_end_is_stable() -> None:
    assert current_season_end(dt.date(2026, 8, 31)) == 2026
    assert current_season_end(dt.date(2026, 3, 1)) == 2025
    assert current_season_end(dt.date(2026, 11, 1)) == 2026
