"""Name resolution, caching, and offline behaviour."""

from __future__ import annotations

import pytest
from swish.config import Settings
from swish.data.cache import Cache
from swish.data.fetch import MAX_AGE_PLAYER, Fetcher
from swish.data.repo import Repo
from swish.errors import PlayerNotFound, SourceUnavailable

from conftest import FixtureFetcher


@pytest.mark.parametrize(
    ("query", "expected_pid"),
    [
        ("Luka Doncic", "doncilu01"),
        ("luka doncic", "doncilu01"),
        ("Luka Dončić", "doncilu01"),
        ("Nikola Jokic", "jokicni01"),
        ("jokic", "jokicni01"),
        ("Bogdan Bogdanovic", "bogdabo01"),
        ("Shai Gilgeous-Alexander", "gilgesh01"),
        ("gilgeous alexander", "gilgesh01"),
        ("doncilu01", "doncilu01"),
    ],
)
def test_resolve_handles_accents_typos_and_ids(repo: Repo, query: str, expected_pid: str):
    assert repo.resolve(query).pid == expected_pid


def test_typo_still_resolves(repo: Repo):
    assert repo.resolve("Luka Doncicc").pid == "doncilu01"


def test_first_name_resolves_via_bref_search(repo: Repo):
    # "luka" is filed under 'd' (Dončić) — the letter index can't place it,
    # so this exercises the search-endpoint fallback
    assert repo.resolve("luka").pid == "doncilu01"


def test_unknown_player_raises(repo: Repo):
    with pytest.raises(PlayerNotFound):
        repo.resolve("Bbbbbq Jjjjjw")


def test_repeated_lookups_hit_the_cache_not_the_network(fixture_fetcher: FixtureFetcher):
    repo = Repo(fixture_fetcher)
    repo.player_card(repo.resolve("doncilu01"))
    first = list(fixture_fetcher.downloads)
    repo.player_card(repo.resolve("doncilu01"))
    assert fixture_fetcher.downloads == first  # no new downloads the second time


def test_cache_persists_between_fetchers(tmp_path):
    cache_file = tmp_path / "c.db"

    class OneShot(Fetcher):
        hits = 0

        def _download(self, url: str) -> str:
            OneShot.hits += 1
            return "<html>ok</html>"

    a = OneShot(Cache(cache_file), Settings(min_interval=0))
    a.get("/players/x/test.html", max_age=MAX_AGE_PLAYER)
    b = OneShot(Cache(cache_file), Settings(min_interval=0))
    b.get("/players/x/test.html", max_age=MAX_AGE_PLAYER)
    assert OneShot.hits == 1


def test_offline_without_cache_is_a_clean_error(tmp_path):
    f = Fetcher(Cache(tmp_path / "c.db"), Settings(offline=True, min_interval=0))
    with pytest.raises(SourceUnavailable):
        f.get("/players/x/nope.html", max_age=MAX_AGE_PLAYER)


def test_search_returns_ranked_matches(repo: Repo):
    hits = repo.search("bogdan")
    assert any(r.pid == "bogdabo01" for r in hits)
