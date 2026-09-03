"""The committed season snapshot: round-trip, and that the app reads it
instead of the network."""

from __future__ import annotations

import pytest
from swish.data.bref import current_season_end
from swish.data.repo import Repo
from swish.data.snapshot import Snapshot, load_snapshot, save_snapshot


@pytest.fixture
def snapshot(repo: Repo) -> Snapshot:
    """A tiny two-player snapshot built from the fixture pages."""
    ctx = repo.season_context(current_season_end())
    cards = {pid: repo.player_card(repo.resolve(pid)) for pid in ("jokicni01", "doncilu01")}
    return Snapshot(current_season_end(), "2026-01-01", ctx, cards)


class _NoNetwork:
    """A fetcher stand-in that fails loudly if the repo reaches for it."""

    settings = type("S", (), {"offline": True})()

    def get(self, *a: object, **k: object) -> str:
        raise AssertionError("touched the network")

    def get_image(self, *a: object, **k: object) -> bytes | None:
        raise AssertionError("touched the network")


def test_round_trip(tmp_path, snapshot: Snapshot) -> None:
    path = tmp_path / "season.json"
    save_snapshot(snapshot, path)
    back = load_snapshot(path)

    assert back is not None
    assert back.season_end == snapshot.season_end
    assert set(back.cards) == set(snapshot.cards)

    a = back.card("doncilu01")
    b = snapshot.card("doncilu01")
    assert a is not None and b is not None
    assert a.bio.name == b.bio.name
    assert a.bio.birth_date == b.bio.birth_date
    assert a.bio.draft_pick == b.bio.draft_pick
    assert a.seasons == b.seasons
    assert a.contract == b.contract
    assert a.salary_history == b.salary_history


def test_missing_file_is_none(tmp_path) -> None:
    assert load_snapshot(tmp_path / "absent.json") is None


def test_repo_answers_from_the_snapshot(snapshot: Snapshot) -> None:
    # _NoNetwork is offline, so anything that reaches past the snapshot fails
    repo = Repo(_NoNetwork(), snapshot=snapshot)

    assert repo.season_context(current_season_end()) is snapshot.context

    card = repo.player_card(repo.resolve("Nikola Jokic"))
    assert card.bio.pid == "jokicni01"

    hits = repo.search("luka")
    assert hits and hits[0].pid == "doncilu01"


def test_repo_falls_back_to_live_off_snapshot(snapshot: Snapshot, repo: Repo) -> None:
    # snapshot holds only Jokic and Doncic; another fixture player still resolves
    blended = Repo(repo.fetch, snapshot=snapshot)
    card = blended.player_card(blended.resolve("Victor Wembanyama"))
    assert card.bio.pid == "wembavi01"


def test_search_blends_live_and_dedupes(snapshot: Snapshot, repo: Repo) -> None:
    # a thin snapshot hit ("jokic") still triggers the live search; the two
    # sources are merged without duplicating him
    blended = Repo(repo.fetch, snapshot=snapshot)
    pids = [h.pid for h in blended.search("jokic")]
    assert pids.count("jokicni01") == 1


def test_committed_snapshot_is_usable() -> None:
    snap = load_snapshot()
    if snap is None:
        pytest.skip("no committed snapshot in this tree")

    assert snap.season_end == current_season_end()
    assert len(snap.cards) >= 100
    for card in snap.cards.values():
        assert card.bio.name
        assert card.seasons, f"{card.bio.pid} has no seasons"


def test_committed_snapshot_ranks_the_bigger_career_first() -> None:
    snap = load_snapshot()
    if snap is None:
        pytest.skip("no committed snapshot in this tree")

    # "luka" matches both Dončić and Garza; the star should win both paths
    assert snap.search("luka")[0].name.endswith("Dončić")
    resolved = snap.resolve("luka")
    assert resolved is not None and resolved.name.endswith("Dončić")
