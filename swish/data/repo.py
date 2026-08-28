"""The one class the rest of Swish talks to for data.

``Repo`` composes :class:`~swish.data.fetch.Fetcher` and the parsers into three
questions:

* :meth:`resolve` — "which player does this string mean?"
* :meth:`player_card` — "give me his career and contract"
* :meth:`season_context` — "give me that season's league-wide advanced stats"
"""

from __future__ import annotations

import contextlib
from concurrent.futures import ThreadPoolExecutor

from swish.data import bref, parse
from swish.data.fetch import (
    MAX_AGE_INDEX,
    MAX_AGE_PLAYER,
    MAX_AGE_SEASON,
    Fetcher,
)
from swish.data.schema import PlayerCard, PlayerRef, SeasonContext
from swish.errors import PlayerNotFound, SwishError


class Repo:
    def __init__(self, fetcher: Fetcher):
        self.fetch = fetcher
        self._index_cache: dict[str, list[PlayerRef]] = {}
        self._context_cache: dict[int, SeasonContext] = {}

    # -- resolve ---------------------------------------------------------

    def resolve(self, query: str) -> PlayerRef:
        query = query.strip()
        if bref.looks_like_pid(query):
            return PlayerRef(
                pid=query,
                name=query,
                url_path=bref.player_url(query),
                from_year=0,
                to_year=bref.current_season_end(),
            )

        # fast path: last-name queries ("jokic", "Nikola Jokic") resolve straight
        # off the letter-index page
        pool: list[PlayerRef] = []
        best: PlayerRef | None = None
        best_score = 0.0
        for letter in bref.index_letters_for(query):
            pool.extend(self._letter_index(letter))
            cand, score, _ = bref.match_player(query, pool)
            if score > best_score:
                best, best_score = cand, score
            if best is not None and best_score >= bref.CONFIDENT:
                return best
        if best is not None:
            return best

        # first names, nicknames, partials and typos go through B-Ref's search
        hits = self.search(query, limit=6)
        if not hits:
            raise PlayerNotFound(query, suggestions=[])
        want = bref.normalize(query)
        exact = next((h for h in hits if bref.normalize(h.name) == want), None)
        if exact is not None:
            return exact
        best = hits[0]
        if want in bref.normalize(best.name) or bref.score_match(query, best) >= 0.5:
            return best
        raise PlayerNotFound(query, suggestions=[h.name for h in hits[:5]])

    def search(self, query: str, limit: int = 8) -> list[PlayerRef]:
        query = query.strip()
        if not query:
            return []
        if bref.looks_like_pid(query):
            return [
                PlayerRef(
                    pid=query,
                    name=query,
                    url_path=bref.player_url(query),
                    from_year=0,
                    to_year=bref.current_season_end(),
                )
            ]
        html = self.fetch.get(bref.search_url(query), max_age=MAX_AGE_SEASON)
        hits = parse.parse_search(html)
        want = bref.normalize(query)
        hits.sort(key=lambda r: (want not in bref.normalize(r.name), -r.to_year))
        return hits[:limit]

    # -- player --------------------------------------------------------

    def player_card(self, ref: PlayerRef | str) -> PlayerCard:
        if isinstance(ref, str):
            ref = self.resolve(ref)
        html = self.fetch.get(ref.url_path, max_age=MAX_AGE_PLAYER)
        soup = parse.soup(html)  # parse the ~1 MB page once, reuse for every table
        upcoming = bref.upcoming_season_end()
        bio = parse.parse_bio(soup, ref.pid)
        if ref.name and not bref.looks_like_pid(ref.name):
            bio = _with_name(bio, ref.name)
        salary_history = parse.parse_salary_history(soup)
        contract = parse.likely_guaranteed(
            parse.parse_contract(soup, from_season_end=upcoming),
            bio=bio,
            salary_history=salary_history,
            from_season_end=upcoming,
        )
        return PlayerCard(
            bio=bio,
            seasons=tuple(parse.parse_seasons(soup)),
            contract=tuple(contract),
            salary_history=tuple(salary_history),
        )

    # -- season context ----------------------------------------------

    def season_context(self, season_end: int) -> SeasonContext:
        if season_end in self._context_cache:
            return self._context_cache[season_end]
        # the two leaderboard pages are independent — fetch them together so a
        # cold context costs one wait, not two
        urls = [bref.season_advanced_url(season_end), bref.season_per_game_url(season_end)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            adv, pg = pool.map(lambda u: self.fetch.get(u, max_age=MAX_AGE_SEASON), urls)
        ctx = parse.parse_season_context(adv, pg, season_end)
        self._context_cache[season_end] = ctx
        return ctx

    def headshot(self, ref: PlayerRef | str) -> bytes | None:
        pid = ref if isinstance(ref, str) else ref.pid
        return self.fetch.get_image(f"/req/202106291/images/headshots/{pid}.jpg", max_age=MAX_AGE_INDEX)

    def prewarm(self, season_end: int | None = None) -> None:
        """Best-effort: pull the current season's context into the cache.

        Called in a background thread on server start so the first user lookup
        only has to fetch the player's own page.
        """
        with contextlib.suppress(SwishError):
            self.season_context(season_end or bref.current_season_end())

    # -- internals --------------------------------------------------

    def _letter_index(self, letter: str) -> list[PlayerRef]:
        if letter not in self._index_cache:
            html = self.fetch.get(bref.index_url(letter), max_age=MAX_AGE_INDEX)
            self._index_cache[letter] = parse.parse_index(html)
        return self._index_cache[letter]


def _with_name(bio, name: str):
    from dataclasses import replace

    return replace(bio, name=name)
