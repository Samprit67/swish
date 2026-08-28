"""Basketball-Reference specifics: URL shapes, season arithmetic, name lookup."""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from difflib import SequenceMatcher

from swish.data.schema import PlayerRef

_PID_RE = re.compile(r"^[a-z]+[0-9]{2}$")


def current_season_end(today: dt.date | None = None) -> int:
    """The season end-year Swish treats as "now".

    An NBA season spans October Y-1 to June Y and is called season ``Y``. From
    July onward the season that just finished is the reference; from January to
    June the season in progress has not finished, so the previous one is.
    """
    day = today or dt.date.today()
    return day.year if day.month >= 7 else day.year - 1


def upcoming_season_end(today: dt.date | None = None) -> int:
    """The first season Swish projects from — the next one to be (or being) played."""
    day = today or dt.date.today()
    return day.year if 1 <= day.month <= 6 else day.year + 1


def player_url(pid: str) -> str:
    return f"/players/{pid[0]}/{pid}.html"


def index_url(letter: str) -> str:
    return f"/players/{letter.lower()}/"


def search_url(query: str) -> str:
    from urllib.parse import quote_plus

    return f"/search/search.fcgi?search={quote_plus(query)}"


def season_advanced_url(season_end: int) -> str:
    return f"/leagues/NBA_{season_end}_advanced.html"


def season_per_game_url(season_end: int) -> str:
    return f"/leagues/NBA_{season_end}_per_game.html"


# --------------------------------------------------------------------------
# name -> player
# --------------------------------------------------------------------------


def normalize(text: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    stripped = stripped.replace("'", "").replace("’", "").replace(".", "")
    return re.sub(r"\s+", " ", stripped).strip().lower()


def looks_like_pid(text: str) -> bool:
    return bool(_PID_RE.match(text.strip()))


def index_letters_for(query: str) -> list[str]:
    """Letter-index pages to try for ``query``, in priority order.

    Basketball-Reference files a player under the first letter of his last name,
    but "last name" is ambiguous for compound names (Gilgeous-Alexander, Van
    Gundy). So: last token first, then hyphen parts of it, then the other
    tokens. Callers fetch these lazily and stop once they have a confident hit.
    """
    tokens = normalize(query).split()
    if not tokens:
        return []
    # last token as written (B-Ref files "Gilgeous-Alexander" under G), then its
    # hyphen parts, then the earlier tokens
    candidates = [tokens[-1], *tokens[-1].split("-"), *tokens[:-1]]
    seen: list[str] = []
    for tok in candidates:
        if tok and tok[0].isalpha() and tok[0] not in seen:
            seen.append(tok[0])
    return seen


#: score at which a single letter-page hit is trusted without checking others
CONFIDENT = 0.90
#: score below which nothing is returned at all
FLOOR = 0.60


def score_match(query: str, ref: PlayerRef) -> float:
    want = normalize(query)
    name = normalize(ref.name)
    ratio = SequenceMatcher(None, want, name).ratio()
    if want and want in name:
        ratio = max(ratio, 0.90 + 0.10 * len(want) / max(len(name), 1))
    if name == want:
        ratio = 1.0
    wt, nt = want.split(), name.split()
    if wt and nt and wt[-1] == nt[-1]:
        ratio += 0.06
    if wt and nt and wt[0] == nt[0]:
        ratio += 0.02
    ratio += min(ref.to_year, current_season_end()) / 1_000_000  # tie-break toward active
    return ratio


def match_player(
    query: str, refs: list[PlayerRef], *, limit: int = 5
) -> tuple[PlayerRef | None, float, list[str]]:
    """Best ref for ``query``, its score, and runner-up names for "did you mean"."""
    scored = sorted(((score_match(query, r), r) for r in refs), key=lambda t: t[0], reverse=True)
    if not scored:
        return None, 0.0, []
    best_score, best = scored[0]
    suggestions = [r.name for _, r in scored[1 : limit + 1]]
    if best_score >= FLOOR:
        return best, best_score, suggestions
    return None, best_score, [best.name, *suggestions][:limit]
