"""Turn Basketball-Reference HTML into the dataclasses in :mod:`swish.data.schema`.

Basketball-Reference is remarkably consistent: every stat cell carries a
``data-stat`` attribute, so we read by name rather than by column position and
the parser survives them adding or reordering columns. A few tables are still
delivered inside HTML comments; :func:`_soup` splices those back in first.
"""

from __future__ import annotations

import datetime as dt
import itertools
import re
from collections.abc import Iterator

from bs4 import BeautifulSoup, Comment, Tag

from swish.data.schema import (
    ContractYear,
    LeagueLine,
    PlayerBio,
    PlayerRef,
    SeasonContext,
    SeasonLine,
)

_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        start=1,
    )
}


# --------------------------------------------------------------------------
# soup helpers
# --------------------------------------------------------------------------


def _soup(html: str | BeautifulSoup) -> BeautifulSoup:
    """Parse HTML, splicing Basketball-Reference's comment-wrapped tables back in.

    Accepts an already-parsed soup and returns it untouched, so callers that need
    several tables off one page can parse once and pass the soup around.
    """
    if isinstance(html, BeautifulSoup):
        return html
    doc = BeautifulSoup(html, "lxml")
    for comment in doc.find_all(string=lambda t: isinstance(t, Comment)):
        if "<table" in comment:
            fragment = BeautifulSoup(str(comment), "lxml")
            comment.replace_with(fragment)
    return doc


#: public alias — parse a page once, then hand the soup to several parse_* calls
soup = _soup


def _rows(table: Tag) -> Iterator[dict[str, str]]:
    """Yield ``{data-stat: text}`` for each real (non-header) body row."""
    body = table.find("tbody")
    if body is None:
        return
    for tr in body.find_all("tr", recursive=False):
        classes = tr.get("class") or []
        if "thead" in classes:
            continue
        cells = tr.find_all(["th", "td"], recursive=False)
        row = {c.get("data-stat"): c.get_text(strip=True) for c in cells}
        pid_cell = tr.find(attrs={"data-append-csv": True})
        if pid_cell is not None:
            row["_pid"] = pid_cell["data-append-csv"]
        yield row


def _num(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return float(value.replace(",", "").lstrip("+"))
    except ValueError:
        return 0.0


def _int(value: str | None) -> int:
    return round(_num(value))


def _money(value: str | None) -> int:
    if not value:
        return 0
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else 0


def _season_end(label: str) -> int | None:
    """``"2025-26"`` → ``2026``; ``"1999-00"`` → ``2000``; ``"2024"`` → ``2024``."""
    label = label.strip()
    m = re.match(r"^(\d{4})-(\d{2})$", label)
    if m:
        start = int(m.group(1))
        return start + 1 if label[-2:] != "00" else (start // 100 + 1) * 100
    if re.match(r"^\d{4}$", label):
        return int(label)
    return None


# --------------------------------------------------------------------------
# letter index  ->  PlayerRef
# --------------------------------------------------------------------------


def parse_index(html: str) -> list[PlayerRef]:
    soup = _soup(html)
    table = soup.find("table", id="players")
    if table is None:
        return []
    refs: list[PlayerRef] = []
    for tr in table.find("tbody").find_all("tr"):
        if "thead" in (tr.get("class") or []):
            continue
        link = tr.find("th").find("a") if tr.find("th") else None
        if link is None:
            continue
        cells = {c.get("data-stat"): c.get_text(strip=True) for c in tr.find_all(["th", "td"])}
        refs.append(
            PlayerRef(
                pid=link["href"].rsplit("/", 1)[-1].removesuffix(".html"),
                name=link.get_text(strip=True).replace("*", "").strip(),
                url_path=link["href"],
                from_year=_int(cells.get("year_min")),
                to_year=_int(cells.get("year_max")),
                position=cells.get("pos", ""),
            )
        )
    return refs


_PLAYER_HREF = re.compile(r"^/players/[a-z]/[a-z]+\d{2}\.html$")
_YEARS = re.compile(r"\((\d{4})-(\d{4})\)\s*$")


def parse_search(html: str | BeautifulSoup) -> list[PlayerRef]:
    """Parse a ``/search/search.fcgi`` results page into NBA player refs.

    This handles first names, partial names and nicknames; the letter-index
    pages can't, because they file each player under his last name only.
    """
    soup = _soup(html)
    out: list[PlayerRef] = []
    seen: set[str] = set()
    for item in soup.select("div.search-item"):
        link = item.select_one(".search-item-name a")
        href = link.get("href", "") if link else ""
        if not _PLAYER_HREF.match(href):
            continue
        pid = href.rsplit("/", 1)[-1].removesuffix(".html")
        if pid in seen:
            continue
        seen.add(pid)
        raw = link.get_text(" ", strip=True)
        years = _YEARS.search(raw)
        team = item.select_one(".search-item-team")
        pos = ""
        if team and "Plays for" in team.get_text():
            pos = team.get_text(strip=True).replace("Plays for:", "").strip()
        out.append(
            PlayerRef(
                pid=pid,
                name=raw[: years.start()].strip() if years else raw,
                url_path=href,
                from_year=int(years.group(1)) if years else 0,
                to_year=int(years.group(2)) if years else 0,
                position=pos,
            )
        )
    return out


# --------------------------------------------------------------------------
# player page  ->  bio / seasons / contract
# --------------------------------------------------------------------------


def parse_bio(html: str, pid: str) -> PlayerBio:
    soup = _soup(html)
    meta = soup.find("div", id="meta")
    name_el = soup.find("h1")
    name = name_el.get_text(strip=True) if name_el else pid

    lines: list[str] = []
    if meta is not None:
        for p in meta.find_all("p"):
            lines.append(re.sub(r"\s+", " ", p.get_text(" ", strip=True)))

    def line_matching(needle: str) -> str:
        return next((ln for ln in lines if needle in ln), "")

    height_in = weight_lb = None
    ft = re.search(r"(\d)-(\d{1,2})\s*,\s*(\d{2,3})lb", line_matching("lb"))
    if ft:
        height_in = int(ft.group(1)) * 12 + int(ft.group(2))
        weight_lb = int(ft.group(3))

    birth = None
    b = re.search(r"Born:\s*([A-Za-z]+)\s+(\d{1,2})\s*,\s*(\d{4})", line_matching("Born:"))
    if b and b.group(1).lower() in _MONTHS:
        birth = dt.date(int(b.group(3)), _MONTHS[b.group(1).lower()], int(b.group(2)))

    draft_year = draft_pick = None
    d = re.search(r"(\d+)\w\w\s+overall\).*?(\d{4})\s+NBA Draft", line_matching("Draft:"))
    if d:
        draft_pick, draft_year = int(d.group(1)), int(d.group(2))

    team = None
    t = re.search(r"Team\s*:\s*(.+?)\s*$", line_matching("Team"))
    if t:
        team = t.group(1).strip()

    positions = ""
    p = re.search(r"Position\s*:\s*(.+?)\s*(?:▪|$)", line_matching("Position"))
    if p:
        positions = p.group(1).strip()

    return PlayerBio(
        pid=pid,
        name=name,
        positions=positions,
        height_in=height_in,
        weight_lb=weight_lb,
        birth_date=birth,
        draft_year=draft_year,
        draft_pick=draft_pick,
        current_team=team,
    )


def parse_seasons(html: str) -> list[SeasonLine]:
    """Merge the per-game and advanced career tables into one row per season."""
    soup = _soup(html)
    per_game = _index_seasons(soup.find("table", id="per_game_stats"))
    advanced = _index_seasons(soup.find("table", id="advanced"))

    lines: list[SeasonLine] = []
    for year, pg in per_game.items():
        if pg.get("comp_name_abbr", "NBA") != "NBA":
            continue
        adv = advanced.get(year, {})
        lines.append(
            SeasonLine(
                season_end=year,
                age=_int(pg.get("age") or adv.get("age")),
                team=pg.get("team_name_abbr", ""),
                position=pg.get("pos", ""),
                games=_int(pg.get("games")),
                games_started=_int(pg.get("games_started")),
                minutes=_int(adv.get("mp")) or _int(pg.get("mp")),
                pts=_num(pg.get("pts_per_g")),
                ast=_num(pg.get("ast_per_g")),
                trb=_num(pg.get("trb_per_g")),
                stl=_num(pg.get("stl_per_g")),
                blk=_num(pg.get("blk_per_g")),
                tov=_num(pg.get("tov_per_g")),
                fg_pct=_num(pg.get("fg_pct")),
                fg3_pct=_num(pg.get("fg3_pct")),
                ft_pct=_num(pg.get("ft_pct")),
                per=_num(adv.get("per")),
                ts_pct=_num(adv.get("ts_pct")),
                usg_pct=_num(adv.get("usg_pct")),
                ows=_num(adv.get("ows")),
                dws=_num(adv.get("dws")),
                ws=_num(adv.get("ws")),
                ws_per_48=_num(adv.get("ws_per_48")),
                obpm=_num(adv.get("obpm")),
                dbpm=_num(adv.get("dbpm")),
                bpm=_num(adv.get("bpm")),
                vorp=_num(adv.get("vorp")),
            )
        )
    lines.sort(key=lambda s: s.season_end)
    return lines


def _index_seasons(table: Tag | None) -> dict[int, dict[str, str]]:
    """First row wins per season — that's Basketball-Reference's combined ``2TM`` row."""
    out: dict[int, dict[str, str]] = {}
    if table is None:
        return out
    for row in _rows(table):
        year = _season_end(row.get("year_id", ""))
        if year is None or year in out:
            continue
        out[year] = row
    return out


def parse_contract(html: str, *, from_season_end: int) -> list[ContractYear]:
    soup = _soup(html)
    table = next(
        (t for t in soup.find_all("table") if (t.get("id") or "").startswith("contracts_")),
        None,
    )
    if table is None:
        return []
    header = table.find("tr", class_="thead") or table.find("tr")
    year_cols = [th.get("data-stat", "") for th in header.find_all(["th", "td"])]
    data_row = None
    for tr in table.find_all("tr"):
        if "thead" in (tr.get("class") or []):
            continue
        if tr.find(["td"]):
            data_row = tr
            break
    if data_row is None:
        return []

    out: list[ContractYear] = []
    cells = data_row.find_all(["th", "td"])
    for col, cell in zip(year_cols, cells, strict=False):
        year = _season_end(col)
        if year is None or year < from_season_end:
            continue
        span = cell.find("span")
        salary = _money(cell.get_text(strip=True))
        if salary <= 0:
            continue
        option = None
        klass = " ".join(span.get("class", [])) if span else ""
        if "salary-pl" in klass:
            option = "player"
        elif "salary-tm" in klass:
            option = "team"
        elif "salary-et" in klass:
            option = "early_termination"
        out.append(ContractYear(season_end=year, salary=salary, option=option))
    out.sort(key=lambda c: c.season_end)
    return out


def likely_guaranteed(
    years: list[ContractYear],
    *,
    bio: PlayerBio,
    salary_history: list[ContractYear],
    from_season_end: int,
) -> list[ContractYear]:
    """Drop Basketball-Reference's *projected* rookie-scale extension years.

    B-Ref appends a player's likely extension to the contract table with no
    marker — a 22-year-old's table shows the real team-option year and then a
    jump to a projected max. If the player is still on a rookie-scale deal, we
    cut the table at the first year that leaps more than 55% over the previous
    one (real NBA raises are capped near 8%).
    """
    if not years:
        return years
    on_rookie_scale = False
    if bio.draft_year is not None and from_season_end - bio.draft_year <= 4:
        past = [s.salary for s in salary_history if s.season_end < from_season_end]
        on_rookie_scale = bool(past) and past[-1] < 15_000_000
    if not on_rookie_scale:
        return years

    kept = [years[0]]
    for prev, year in itertools.pairwise(years):
        if year.salary > 1.55 * prev.salary:
            break
        kept.append(year)
    return kept


def parse_salary_history(html: str) -> list[ContractYear]:
    soup = _soup(html)
    table = soup.find("table", id="all_salaries")
    if table is None:
        return []
    out: list[ContractYear] = []
    for row in _rows(table):
        year = _season_end(row.get("season", ""))
        if year is None:
            continue
        out.append(ContractYear(season_end=year, salary=_money(row.get("salary"))))
    out.sort(key=lambda c: c.season_end)
    return out


# --------------------------------------------------------------------------
# season leaderboard  ->  SeasonContext
# --------------------------------------------------------------------------


def parse_season_context(advanced_html: str, per_game_html: str, season_end: int) -> SeasonContext:
    adv = _index_league(_soup(advanced_html).find("table", id="advanced"))
    pg = _index_league(_soup(per_game_html).find("table", id="per_game_stats"))

    lines: list[LeagueLine] = []
    for pid, a in adv.items():
        p = pg.get(pid, {})
        lines.append(
            LeagueLine(
                pid=pid,
                name=a.get("name_display", ""),
                age=_int(a.get("age")),
                minutes=_int(a.get("mp")),
                games=_int(a.get("games")),
                pts=_num(p.get("pts_per_g")),
                ast=_num(p.get("ast_per_g")),
                trb=_num(p.get("trb_per_g")),
                stl=_num(p.get("stl_per_g")),
                blk=_num(p.get("blk_per_g")),
                ts_pct=_num(a.get("ts_pct")),
                usg_pct=_num(a.get("usg_pct")),
                ws=_num(a.get("ws")),
                ws_per_48=_num(a.get("ws_per_48")),
                bpm=_num(a.get("bpm")),
                vorp=_num(a.get("vorp")),
            )
        )
    return SeasonContext(season_end=season_end, lines=tuple(lines))


def _index_league(table: Tag | None) -> dict[str, dict[str, str]]:
    """One row per player id — the combined row again wins for traded players."""
    out: dict[str, dict[str, str]] = {}
    if table is None:
        return out
    for row in _rows(table):
        pid = row.get("_pid")
        if pid and pid not in out:
            out[pid] = row
    return out
