"""CLI tests — the fixture repo is patched in so nothing hits the network."""

from __future__ import annotations

import json

import pytest
from swish import cli
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture(autouse=True)
def _patch_repo(monkeypatch, repo):
    monkeypatch.setattr(cli, "_repo", lambda: repo)


def test_version():
    result = runner.invoke(cli.app, ["version"])
    assert result.exit_code == 0
    assert "swish" in result.stdout


def test_value_prints_a_breakdown():
    result = runner.invoke(cli.app, ["value", "Nikola Jokic"])
    assert result.exit_code == 0, result.output
    assert "Nikola Jokić" in result.stdout
    assert "Swish value" in result.stdout
    assert "Projection" in result.stdout


def test_value_json_is_parseable():
    result = runner.invoke(cli.app, ["value", "jokicni01", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["player"]["name"] == "Nikola Jokić"
    assert payload["swish_value"] > 0


def test_value_unknown_player_exits_nonzero():
    result = runner.invoke(cli.app, ["value", "Bbbbbq Jjjjjw"])
    assert result.exit_code == 1
    assert "✗" in result.output


def test_compare_ranks_players():
    result = runner.invoke(cli.app, ["compare", "Chris Paul", "Nikola Jokic"])
    assert result.exit_code == 0
    # Jokić should be ranked first
    lines = [ln for ln in result.stdout.splitlines() if "Joki" in ln or "Paul" in ln]
    assert "Joki" in lines[0]


def test_trade_gives_a_verdict():
    result = runner.invoke(cli.app, ["trade", "--a", "jokicni01", "--b", "banchpa01,bogdabo01"])
    assert result.exit_code == 0
    assert "Side B wins" in result.stdout


def test_leaderboard():
    result = runner.invoke(cli.app, ["leaderboard", "--top", "10"])
    assert result.exit_code == 0
    assert "production value" in result.stdout


def test_fetch_reports_success():
    result = runner.invoke(cli.app, ["fetch", "Luka Doncic"])
    assert result.exit_code == 0
    assert "cached Luka Dončić" in result.stdout


def test_data_info():
    from swish.data.snapshot import load_snapshot

    result = runner.invoke(cli.app, ["data", "info"])
    if load_snapshot() is None:
        assert result.exit_code == 1
    else:
        assert result.exit_code == 0
        assert "players" in result.stdout
