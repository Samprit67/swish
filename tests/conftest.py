"""Test rig.

Everything runs offline. ``fixture_fetcher`` is a :class:`~swish.data.fetch.Fetcher`
whose network seam is replaced with a lookup into ``tests/fixtures/*.html.gz`` —
real Basketball-Reference pages captured once. If a test asks for a URL that
wasn't captured, it fails loudly rather than hitting the network.
"""

from __future__ import annotations

import gzip
import pathlib

import pytest
from swish.config import Settings
from swish.data.cache import Cache
from swish.data.fetch import Fetcher
from swish.data.repo import Repo

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

# url path  ->  fixture file
_ROUTES = {
    "/players/d/doncilu01.html": "player_doncilu01.html.gz",
    "/players/j/jokicni01.html": "player_jokicni01.html.gz",
    "/players/b/banchpa01.html": "player_banchpa01.html.gz",
    "/players/p/paulch01.html": "player_paulch01.html.gz",
    "/players/b/bogdabo01.html": "player_bogdabo01.html.gz",
    "/players/w/wembavi01.html": "player_wembavi01.html.gz",
    "/players/g/gilgesh01.html": "player_gilgesh01.html.gz",
    "/players/t/thompam01.html": "player_thompam01.html.gz",
    "/players/a/": "index_a.html.gz",
    "/players/l/": "index_l.html.gz",
    "/players/d/": "index_d.html.gz",
    "/players/b/": "index_b.html.gz",
    "/players/j/": "index_j.html.gz",
    "/players/p/": "index_p.html.gz",
    "/players/w/": "index_w.html.gz",
    "/players/g/": "index_g.html.gz",
    "/players/t/": "index_t.html.gz",
    "/leagues/NBA_2026_advanced.html": "season_2026_advanced.html.gz",
    "/leagues/NBA_2026_per_game.html": "season_2026_per_game.html.gz",
    "/leagues/NBA_2025_advanced.html": "season_2025_advanced.html.gz",
    "/leagues/NBA_2025_per_game.html": "season_2025_per_game.html.gz",
}


def load_fixture(name: str) -> str:
    return gzip.decompress((FIXTURES / name).read_bytes()).decode("utf-8", "replace")


class FixtureFetcher(Fetcher):
    """A Fetcher that reads recorded HTML instead of hitting the network."""

    def __init__(self, cache: Cache | None = None):
        super().__init__(cache or Cache(":memory:"), Settings(min_interval=0.0))
        self.downloads: list[str] = []

    def _download(self, url: str) -> str:
        path = url.replace("https://www.basketball-reference.com", "")
        if path not in _ROUTES:
            raise AssertionError(f"no fixture for {path!r} — capture it or fix the test")
        self.downloads.append(path)
        return load_fixture(_ROUTES[path])


@pytest.fixture
def fixture_fetcher() -> FixtureFetcher:
    return FixtureFetcher()


@pytest.fixture(scope="session")
def _session_repo() -> Repo:
    # HTML parsing (esp. the 700-row season tables) is the expensive bit; parse
    # once and share the Repo's in-memory caches across the read-only tests.
    return Repo(FixtureFetcher())


@pytest.fixture
def repo(_session_repo: Repo) -> Repo:
    return _session_repo


@pytest.fixture
def client(repo: Repo):
    from fastapi.testclient import TestClient
    from swish.api import create_app

    app = create_app(Settings(cache_path=":memory:"), repo=repo)
    with TestClient(app) as c:
        yield c
