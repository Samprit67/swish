"""The typed shapes the rest of Swish works with.

These are deliberately plain: frozen dataclasses of built-in types, no methods
that do real work. Parsing fills them in (:mod:`swish.data.parse`); the model
reads them (:mod:`swish.model`).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlayerRef:
    """A player as listed on a Basketball-Reference letter index."""

    pid: str  # basketball-reference id, e.g. "doncilu01"
    name: str  # "Luka Dončić"
    url_path: str  # "/players/d/doncilu01.html"
    from_year: int  # first season end year
    to_year: int  # last season end year (current year ⇒ still active)
    position: str = ""


@dataclass(frozen=True)
class PlayerBio:
    pid: str
    name: str
    positions: str = ""
    height_in: int | None = None
    weight_lb: int | None = None
    birth_date: dt.date | None = None
    draft_year: int | None = None
    draft_pick: int | None = None  # overall pick number
    current_team: str | None = None

    def age_on(self, day: dt.date) -> float | None:
        """Fractional age on ``day`` — used to place the player on the age curve."""
        if self.birth_date is None:
            return None
        return (day - self.birth_date).days / 365.25


@dataclass(frozen=True)
class SeasonLine:
    """One player-season, combining the per-game and advanced tables.

    Multi-team seasons collapse to the ``TOT``/``2TM`` combined row.
    """

    season_end: int  # 2026 == the 2025-26 season
    age: int  # basketball-reference age (age on Feb 1 of the season)
    team: str
    position: str
    games: int
    games_started: int
    minutes: int  # total minutes played

    # per game
    pts: float = 0.0
    ast: float = 0.0
    trb: float = 0.0
    stl: float = 0.0
    blk: float = 0.0
    tov: float = 0.0
    fg_pct: float = 0.0
    fg3_pct: float = 0.0
    ft_pct: float = 0.0

    # advanced
    per: float = 0.0
    ts_pct: float = 0.0
    usg_pct: float = 0.0
    ows: float = 0.0
    dws: float = 0.0
    ws: float = 0.0
    ws_per_48: float = 0.0
    obpm: float = 0.0
    dbpm: float = 0.0
    bpm: float = 0.0
    vorp: float = 0.0

    @property
    def label(self) -> str:
        return f"{self.season_end - 1}-{str(self.season_end)[2:]}"


OPTION_LABELS = {
    "player": "player option",
    "team": "team option",
    "early_termination": "early-termination option",
    "unknown": "non-guaranteed",
}


@dataclass(frozen=True)
class ContractYear:
    season_end: int
    salary: int  # US dollars
    option: str | None = None  # None ⇒ fully guaranteed; else a key of OPTION_LABELS

    @property
    def label(self) -> str:
        return f"{self.season_end - 1}-{str(self.season_end)[2:]}"

    @property
    def guaranteed(self) -> bool:
        return self.option is None


@dataclass(frozen=True)
class PlayerCard:
    """Everything Swish knows about one player after a single page fetch."""

    bio: PlayerBio
    seasons: tuple[SeasonLine, ...] = ()  # regular season, NBA only, ascending
    contract: tuple[ContractYear, ...] = ()  # future guaranteed salary, ascending
    salary_history: tuple[ContractYear, ...] = ()

    @property
    def last_season(self) -> SeasonLine | None:
        return self.seasons[-1] if self.seasons else None

    def recent(self, n: int) -> tuple[SeasonLine, ...]:
        return self.seasons[-n:]


@dataclass(frozen=True)
class LeagueLine:
    """A single row of a season-wide advanced/per-game leaderboard.

    Only the fields Swish uses for percentile context and replacement level.
    """

    pid: str
    name: str
    age: int
    minutes: int
    games: int
    pts: float = 0.0
    ast: float = 0.0
    trb: float = 0.0
    stl: float = 0.0
    blk: float = 0.0
    ts_pct: float = 0.0
    usg_pct: float = 0.0
    ws: float = 0.0
    ws_per_48: float = 0.0
    bpm: float = 0.0
    vorp: float = 0.0


@dataclass(frozen=True)
class SeasonContext:
    """A whole season of league advanced stats, for ranking one player against."""

    season_end: int
    lines: tuple[LeagueLine, ...] = field(default=())

    def qualified(self, min_minutes: int = 500) -> list[LeagueLine]:
        return [line for line in self.lines if line.minutes >= min_minutes]
