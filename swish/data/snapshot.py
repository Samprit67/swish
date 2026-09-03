"""A committed snapshot of one NBA season.

Swish normally reads Basketball-Reference on demand. That is fine on a machine
whose cache has filled up over weeks, but a fresh deploy starts cold: the first
lookup of every player has to download and parse his page (about a megabyte of
HTML), and small hosts throttle outbound requests on top of that.

So this module builds a small JSON file, committed to the repo, holding the
season's league context and the parsed cards of its rotation players. The
running app reads that first and answers instantly for anyone who matters in a
trade; it only touches the network for the long tail (deep bench, retired
players, obscure name spellings).

``build_snapshot`` is dev-only: run ``swish data build`` after the season moves
on. ``load_snapshot`` is what the app calls on start.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from swish.data import bref
from swish.data.schema import (
    ContractYear,
    LeagueLine,
    PlayerBio,
    PlayerCard,
    PlayerRef,
    SeasonContext,
    SeasonLine,
)
from swish.errors import SwishError

#: the committed file the app loads on start
SNAPSHOT_PATH = Path(__file__).parent / "season.json"

#: how many players (ranked by minutes) to capture by default. Deep enough that
#: the cutoff sits below a star who missed a stretch of the season.
DEFAULT_TOP = 320

#: names always worth including even after a lost season, so a search for one of
#: them still resolves offline (the model just flags the stale sample)
MARQUEE = (
    "Jayson Tatum",
    "Anthony Davis",
    "Trae Young",
    "Ja Morant",
    "Kyrie Irving",
    "Damian Lillard",
    "Tyrese Haliburton",
    "Kristaps Porzingis",
    "Fred VanVleet",
    "Jrue Holiday",
)

ProgressFn = Callable[[int, int, str], None]


# -- read side (used by the app) -------------------------------------------


class Snapshot:
    """One season's league context plus the cards of its rotation players."""

    def __init__(
        self,
        season_end: int,
        built_at: str,
        context: SeasonContext,
        cards: dict[str, PlayerCard],
    ) -> None:
        self.season_end = season_end
        self.built_at = built_at
        self.context = context
        self.cards = cards
        self.refs = [self._ref(card) for card in cards.values()]

    def card(self, pid: str) -> PlayerCard | None:
        return self.cards.get(pid)

    def resolve(self, query: str) -> PlayerRef | None:
        """A confident name match, or ``None`` to let the live path try."""
        q = query.strip()
        if not q:
            return None
        if bref.looks_like_pid(q):
            card = self.cards.get(q)
            return self._ref(card) if card is not None else None
        ranked = self._ranked(q)
        if not ranked or ranked[0][0] < bref.CONFIDENT:
            return None
        top = ranked[0][0]
        # a bare last name can tie two players ("luka" -> Dončić and Garza);
        # break it toward the bigger career
        close = [r for s, r in ranked if s >= top - 0.03]
        if len(close) > 1:
            return max(close, key=lambda r: self._career_minutes(r.pid))
        return ranked[0][1]

    def search(self, query: str, limit: int = 8) -> list[PlayerRef]:
        q = query.strip()
        if not q:
            return []
        want = bref.normalize(q)
        hits = [r for s, r in self._ranked(q) if s >= 0.55 or (want and want in bref.normalize(r.name))]
        return hits[:limit]

    def _ranked(self, query: str) -> list[tuple[float, PlayerRef]]:
        # rank by: does a name word match the query (exact, then prefix), then
        # the fuzzy score, then career size. So "ja" leads with Morant not
        # James, and "luka" with Dončić not Garza.
        want = bref.normalize(query)

        def key(pair: tuple[float, PlayerRef]) -> tuple[int, float, int]:
            score, ref = pair
            words = bref.normalize(ref.name).split()
            word_match = max(
                (2 if w == want else 1 if w.startswith(want) else 0 for w in words),
                default=0,
            )
            return (word_match, round(score, 1), self._career_minutes(ref.pid))

        return sorted(
            ((bref.score_match(query, r), r) for r in self.refs),
            key=key,
            reverse=True,
        )

    def _career_minutes(self, pid: str) -> int:
        card = self.cards.get(pid)
        return sum(s.minutes for s in card.seasons) if card is not None else 0

    @staticmethod
    def _ref(card: PlayerCard) -> PlayerRef:
        first = card.seasons[0].season_end if card.seasons else 0
        last = card.seasons[-1] if card.seasons else None
        return PlayerRef(
            pid=card.bio.pid,
            name=card.bio.name,
            url_path=bref.player_url(card.bio.pid),
            from_year=first,
            to_year=last.season_end if last is not None else 0,
            position=last.position if last is not None else "",
        )


def load_snapshot(path: Path = SNAPSHOT_PATH) -> Snapshot | None:
    """Read the committed snapshot, or ``None`` if it is missing or unreadable."""
    try:
        raw = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    try:
        return Snapshot(
            season_end=int(raw["season_end"]),
            built_at=str(raw.get("built_at", "")),
            context=_context_from(raw["context"]),
            cards={pid: _card_from(c) for pid, c in raw["cards"].items()},
        )
    except (KeyError, TypeError, ValueError):
        return None


# -- build side (dev-only) -------------------------------------------------


def build_snapshot(
    repo: Any,
    season_end: int,
    top: int = DEFAULT_TOP,
    progress: ProgressFn | None = None,
) -> tuple[Snapshot, list[str]]:
    """Fetch the season context and the top ``top`` players into a snapshot.

    ``repo`` must be a live :class:`~swish.data.repo.Repo` (no snapshot of its
    own). Returns the snapshot and the names of any players that could not be
    fetched.
    """
    context = repo.season_context(season_end)
    ranked = sorted(context.lines, key=lambda ln: ln.minutes, reverse=True)
    picks = [ln for ln in ranked if ln.pid][:top]
    total = len(picks) + len(MARQUEE)

    cards: dict[str, PlayerCard] = {}
    failed: list[str] = []
    for i, line in enumerate(picks, start=1):
        if progress is not None:
            progress(i, total, line.name)
        ref = PlayerRef(
            pid=line.pid,
            name=line.name,
            url_path=bref.player_url(line.pid),
            from_year=0,
            to_year=season_end,
        )
        try:
            cards[line.pid] = repo.player_card(ref)
        except SwishError:
            failed.append(line.name)

    for j, name in enumerate(MARQUEE, start=len(picks) + 1):
        if progress is not None:
            progress(j, total, name)
        try:
            ref = repo.resolve(name)
            if ref.pid not in cards:
                cards[ref.pid] = repo.player_card(ref)
        except SwishError:
            failed.append(name)

    snap = Snapshot(
        season_end=season_end,
        built_at=dt.date.today().isoformat(),
        context=context,
        cards=cards,
    )
    return snap, failed


def save_snapshot(snap: Snapshot, path: Path = SNAPSHOT_PATH) -> None:
    payload = {
        "season_end": snap.season_end,
        "built_at": snap.built_at,
        "context": dataclasses.asdict(snap.context),
        "cards": {pid: dataclasses.asdict(card) for pid, card in sorted(snap.cards.items())},
    }
    text = json.dumps(payload, default=_json_default, separators=(",", ":"), sort_keys=True)
    path.write_text(text + "\n", "utf-8")


# -- (de)serialisation ----------------------------------------------------


def _json_default(o: object) -> str:
    if isinstance(o, dt.date):
        return o.isoformat()
    raise TypeError(f"cannot serialise {type(o).__name__}")


def _only(cls: type, d: dict) -> dict:
    keep = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in d.items() if k in keep}


def _bio_from(d: dict) -> PlayerBio:
    born = d.get("birth_date")
    return PlayerBio(
        pid=d["pid"],
        name=d["name"],
        positions=d.get("positions", ""),
        height_in=d.get("height_in"),
        weight_lb=d.get("weight_lb"),
        birth_date=dt.date.fromisoformat(born) if born else None,
        draft_year=d.get("draft_year"),
        draft_pick=d.get("draft_pick"),
        current_team=d.get("current_team"),
    )


def _card_from(d: dict) -> PlayerCard:
    return PlayerCard(
        bio=_bio_from(d["bio"]),
        seasons=tuple(SeasonLine(**_only(SeasonLine, s)) for s in d.get("seasons", [])),
        contract=tuple(ContractYear(**_only(ContractYear, c)) for c in d.get("contract", [])),
        salary_history=tuple(ContractYear(**_only(ContractYear, c)) for c in d.get("salary_history", [])),
    )


def _context_from(d: dict) -> SeasonContext:
    return SeasonContext(
        season_end=int(d["season_end"]),
        lines=tuple(LeagueLine(**_only(LeagueLine, ln)) for ln in d.get("lines", [])),
    )
