"""``swish`` — the command line.

swish value "Luka Doncic"                 # trade-value breakdown
swish compare "Luka Doncic" "Jayson Tatum"
swish trade --a "Zion Williamson" --b "Jaylen Brown"
swish leaderboard --season 2026 --top 25
swish serve                               # web dashboard
swish fetch "Nikola Jokic"                # warm the cache
swish cache info
"""

from __future__ import annotations

import json as jsonlib
import time

import typer
from rich.console import Console
from rich.table import Table

from swish import __version__
from swish.api.params import build_params
from swish.api.present import valuation_dict
from swish.config import settings_from_env
from swish.data.bref import current_season_end
from swish.data.cache import Cache
from swish.data.fetch import Fetcher
from swish.data.repo import Repo
from swish.errors import SwishError
from swish.model import evaluate
from swish.model.leaderboard import leaderboard as compute_leaderboard

app = typer.Typer(
    add_completion=False,
    help="Estimate an NBA player's trade value from his stats and contract.",
    no_args_is_help=True,
)
console = Console()


def _repo() -> Repo:
    settings = settings_from_env()
    settings.ensure_dirs()
    return Repo(Fetcher(Cache(settings.cache_url), settings))


def _m(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value) / 1_000_000:,.1f}M"


def _fail(exc: Exception) -> None:
    console.print(f"[bold red]✗[/] {exc}")
    raise typer.Exit(1)


# --------------------------------------------------------------------------


@app.command()
def version() -> None:
    """Print the version."""
    console.print(f"swish {__version__}")


@app.command()
def value(
    name: str = typer.Argument(..., help="NBA player name or basketball-reference id"),
    horizon: int = typer.Option(3, help="Seasons to project (1-5)."),
    discount: float | None = typer.Option(None, help="Annual discount rate, e.g. 0.08."),
    dollars_per_win: float | None = typer.Option(None, "--dpw", help="$ per win, in millions."),
    metric: str | None = typer.Option(None, help="vorp | ws | blend"),
    no_contract: bool = typer.Option(False, "--no-contract", help="Ignore salary; on-court value only."),
    as_json: bool = typer.Option(False, "--json", help="Emit the full breakdown as JSON."),
) -> None:
    """Estimate one player's trade value."""
    try:
        repo = _repo()
        params = build_params(
            horizon=horizon, discount=discount, dollars_per_win=dollars_per_win, metric=metric
        )
        card = repo.player_card(repo.resolve(name))
        ctx = repo.season_context(current_season_end())
        v = evaluate(card, ctx, params, use_contract=not no_contract)
    except SwishError as exc:
        _fail(exc)

    if as_json:
        console.print_json(jsonlib.dumps(valuation_dict(v, full=True)))
        return

    _render_valuation(v)


@app.command()
def compare(
    names: list[str] = typer.Argument(..., help="Two to four players."),
    horizon: int = typer.Option(3),
    no_contract: bool = typer.Option(False, "--no-contract"),
) -> None:
    """Rank two to four players by trade value."""
    if not 2 <= len(names) <= 4:
        _fail(SwishError("Give between two and four players."))
    try:
        repo = _repo()
        ctx = repo.season_context(current_season_end())
        params = build_params(horizon=horizon)
        vals = [
            evaluate(repo.player_card(repo.resolve(n)), ctx, params, use_contract=not no_contract)
            for n in names
        ]
    except SwishError as exc:
        _fail(exc)

    vals.sort(key=lambda v: v.headline_value, reverse=True)
    table = Table(title="Trade value", header_style="bold")
    for col in ("#", "Player", "Age", "Talent WAR", "Swish value", "10th–90th", "≈ pick"):
        table.add_column(col)
    for i, v in enumerate(vals, 1):
        table.add_row(
            str(i),
            v.player.name,
            str(v.projections[0].age - 1),
            f"{v.talent.war:.1f}",
            _m(v.headline_value),
            f"{_m(v.simulation.headline.p10)} – {_m(v.simulation.headline.p90)}",
            v.pick.text,
        )
    console.print(table)


@app.command()
def trade(
    a: str = typer.Option(..., "--a", help="Comma-separated players Side A sends."),
    b: str = typer.Option(..., "--b", help="Comma-separated players Side B sends."),
    horizon: int = typer.Option(3),
) -> None:
    """Weigh a trade: does the value balance?"""
    try:
        repo = _repo()
        ctx = repo.season_context(current_season_end())
        params = build_params(horizon=horizon)

        def side(spec: str) -> list:
            return [
                evaluate(repo.player_card(repo.resolve(n.strip())), ctx, params)
                for n in spec.split(",")
                if n.strip()
            ]

        side_a, side_b = side(a), side(b)
    except SwishError as exc:
        _fail(exc)

    sends_a = sum(v.headline_value for v in side_a)
    sends_b = sum(v.headline_value for v in side_b)
    net_a = sends_b - sends_a

    for label, players, sends in (("Side A sends", side_a, sends_a), ("Side B sends", side_b, sends_b)):
        t = Table(title=label, header_style="bold")
        for col in ("Player", "Swish value"):
            t.add_column(col)
        for v in players:
            t.add_row(v.player.name, _m(v.headline_value))
        t.add_row("[dim]total[/]", f"[bold]{_m(sends)}[/]")
        console.print(t)

    scale = max(abs(sends_a), abs(sends_b), 5_000_000.0)
    if abs(net_a) / scale < 0.12:
        verdict = "[bold green]Roughly fair.[/]"
    elif net_a > 0:
        verdict = f"[bold]Side A wins[/] by {_m(abs(net_a))}."
    else:
        verdict = f"[bold]Side B wins[/] by {_m(abs(net_a))}."
    console.print(verdict)


@app.command()
def leaderboard(
    season: int | None = typer.Option(None, "--season", help="Season end year, e.g. 2026."),
    top: int = typer.Option(25, help="How many to list."),
    min_minutes: int = typer.Option(1000, "--min-minutes"),
) -> None:
    """League leaders by on-court production value (no contract)."""
    try:
        repo = _repo()
        season_end = season or current_season_end()
        board = compute_leaderboard(repo.season_context(season_end), min_minutes=min_minutes)[:top]
    except SwishError as exc:
        _fail(exc)

    table = Table(title=f"{season_end - 1}-{str(season_end)[2:]} production value", header_style="bold")
    for col in ("#", "Player", "Age", "MP", "WAR", "Value"):
        table.add_column(col)
    for i, q in enumerate(board, 1):
        table.add_row(str(i), q.name, str(q.age), str(q.minutes), f"{q.war:.1f}", _m(q.production_value))
    console.print(table)


@app.command()
def fetch(name: str = typer.Argument(..., help="Player to pull into the cache.")) -> None:
    """Warm the cache for a player (and the current season) so later lookups are instant."""
    try:
        repo = _repo()
        started = time.monotonic()
        ref = repo.resolve(name)
        repo.player_card(ref)
        repo.season_context(current_season_end())
    except SwishError as exc:
        _fail(exc)
    console.print(f"[green]✓[/] cached {ref.name} in {time.monotonic() - started:.1f}s")


cache_app = typer.Typer(help="Inspect or clear the local page cache.")
app.add_typer(cache_app, name="cache")


@cache_app.command("info")
def cache_info() -> None:
    settings = settings_from_env()
    stats = Cache(settings.cache_url).stats()
    age = ""
    if stats["oldest"]:
        age = f", oldest {(time.time() - stats['oldest']) / 86400:.1f} days"
    console.print(
        f"{stats['pages']} pages, {stats['bytes'] / 1_000_000:.1f} MB{age}\n[dim]{stats['path']}[/]"
    )


@cache_app.command("clear")
def cache_clear() -> None:
    settings = settings_from_env()
    n = Cache(settings.cache_url).clear()
    console.print(f"[green]✓[/] cleared {n} cached pages")


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Bind address (default 127.0.0.1)."),
    port: int | None = typer.Option(None, help="Port (default 8770)."),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open a browser tab."),
) -> None:
    """Start the web dashboard."""
    import uvicorn

    from swish.api import create_app

    settings = settings_from_env()
    if host:
        settings.host = host
    if port:
        settings.port = port
    settings.ensure_dirs()

    app_ = create_app(settings)
    url = f"http://{settings.host}:{settings.port}"
    console.print(f"swish → [link={url}]{url}[/]")
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(app_, host=settings.host, port=settings.port, log_level="warning")


# --------------------------------------------------------------------------


def _render_valuation(v) -> None:
    from rich.panel import Panel

    p10 = v.simulation.headline.p10
    p90 = v.simulation.headline.p90
    kind = "surplus over contract" if v.used_contract else "on-court production value"
    head = (
        f"[bold]{v.player.name}[/]  ·  {v.player.current_team or 'free agent'}\n"
        f"[bold cyan]{_m(v.headline_value)}[/]  Swish value  [dim]({kind})[/]\n"
        f"range {_m(p10)} – {_m(p90)}   ·   ≈ {v.pick.text}\n"
        f"true-talent WAR {v.talent.war:.1f}   ·   projecting {v.first_projected_season - 1}"
        f"-{str(v.first_projected_season)[2:]} onward"
    )
    console.print(Panel(head, expand=False))

    proj = Table(title="Projection", header_style="bold")
    for col in ("Season", "Age", "Age mult", "Avail", "WAR", "Prod value", "Salary", "Surplus"):
        proj.add_column(col)
    for y, yv in zip(v.projections, v.value.years, strict=True):
        proj.add_row(
            yv_label(yv.season_end),
            str(y.age),
            f"{y.age_multiplier:.2f}",
            f"{y.availability:.0%}",
            f"{y.war:.1f}",
            _m(yv.production_value),
            _m(yv.salary) if v.used_contract else "—",
            _m(yv.surplus),
        )
    console.print(proj)

    if v.percentiles:
        pct = Table(title="League rank (this season)", header_style="bold")
        pct.add_column("Skill")
        pct.add_column("Value")
        pct.add_column("Percentile")
        for pc in v.percentiles:
            bar = "█" * round(pc.percentile / 5)
            pct.add_row(pc.label, f"{pc.value:g}", f"{bar} {pc.percentile:.0f}")
        console.print(pct)

    for note in v.notes:
        console.print(f"[yellow]•[/] [dim]{note}[/]")


def yv_label(season_end: int) -> str:
    return f"{season_end - 1}-{str(season_end)[2:]}"


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
