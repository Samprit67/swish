# 🏀 Swish

**Estimate an NBA player's trade value from his stats and his contract.**

Type in a name. Swish pulls the player's career from Basketball-Reference,
projects his production forward with an age curve, prices those wins in dollars,
subtracts what he's owed, and tells you what the asset is actually worth — on a
scale you can read as draft picks, with an honest uncertainty band.

<p align="center">
  <img src="docs/screenshots/player.png" alt="Swish — player valuation" width="900">
</p>

```bash
pip install -e .
swish value "Nikola Jokic"      # full breakdown in the terminal
swish serve                     # dashboard at http://127.0.0.1:8770
```

---

## Why I built this

Every trade deadline the same argument happens: *is this a fair deal?* The way
analysts actually answer it is a rough mental model — how good is the player,
how long is he good for, what's he getting paid, how does that stack against a
draft pick. I wanted to write that model down so it's explicit and reproducible
instead of vibes, and so I could point it at any player and get a number back.

The interesting part isn't scraping stats — it's the chain from **a stat line to
a dollar figure**: converting box-score metrics to wins without letting the best
players run away to absurd numbers, regressing a noisy single season toward
something stable, aging the projection, and pricing wins in a way that reflects
that a superstar on one roster spot is worth more than three good role players.
That model lives in [`swish/model/`](swish/model/) and is written up in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

It is deliberately not a fan. It prices Dallas trading Luka Dončić as more
defensible than the consensus reaction; it is bearish on young high-volume
scorers whose all-in-one metrics haven't caught up. Whether that's the model
being wrong or being early is left to the reader.

## What it does

| | |
|---|---|
| **Any player** | Resolves a name (accents, typos, `"gilgeous alexander"`, or a raw B-Ref id) against the full player index and fetches him live. |
| **A trade-value number** | Projected wins × the market price of a win, discounted and cap-inflated, minus guaranteed salary → *surplus value*, expressed as `≈ the #7 pick`. |
| **The whole chain, shown** | Career WAR trajectory, the aging projection with a p10–p90 fan, a waterfall from production value to salary to surplus, league percentile bars, a skill radar on compare — every intermediate number the model computed. |
| **Uncertainty** | A ~5,000-run Monte Carlo over talent, aging, health and $/win gives a 10th–90th percentile range, not just a point estimate. |
| **Live analytics** | Sliders for horizon, discount rate and $/win; toggles for the metric (VORP / Win Shares / blend) and whether to subtract salary. Everything recomputes. |
| **Compare** | Two to four players side by side — value bars and skill percentiles. |
| **Trade calculator** | Put players on each side; Swish weighs what each team gives up against what it gets back and calls it. |
| **Leaderboard** | League-wide production-value leaders for a season (fast — one request, no contracts). |
| **Local-first** | Every page fetched from Basketball-Reference is cached in SQLite. Second lookup is instant and works with the network off. |
| **CLI too** | `swish value`, `compare`, `trade`, `leaderboard` for people who live in the terminal, all with `--json`. |

## Screenshots

| Compare | Trade calculator | Leaderboard |
|---|---|---|
| ![](docs/screenshots/compare.png) | ![](docs/screenshots/trade.png) | ![](docs/screenshots/leaderboard.png) |

## Quickstart

```bash
git clone https://github.com/sgoswami/swish
cd swish
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

swish value "Victor Wembanyama"
swish compare "Luka Doncic" "Shai Gilgeous-Alexander" "Jayson Tatum"
swish trade --a "Zion Williamson" --b "Jaylen Brown"
swish serve
```

The first lookup of a player makes one or two requests to
basketball-reference.com (~1–2s — the server warms the league context in the
background on startup, and a token-bucket throttle lets a cold lookup burst).
After that it's served from the cache at
`~/Library/Application Support/swish/cache.db` (macOS) or `$XDG_DATA_HOME/swish`
(Linux). `swish cache info` shows what's stored; `swish cache clear` empties it.

## How the number is built

```
name ──► basketball-reference.com ──► career per-game + advanced + contract
                                          │
  1. blend VORP and Win Shares ──► wins above replacement (calibrated)
  2. regress the last 3 seasons toward the player's own recent form
  3. age curve ──► project the next N seasons
  4. price the wins  (~$3.3M each, cap-grown, discounted, star premium)
  5. subtract guaranteed salary ──► surplus value
  6. map onto a draft-pick-value curve ──► "≈ the #7 pick"
  7. resample everything ~5,000× ──► p10 / p50 / p90
```

Every step is a pure, typed function over plain dataclasses; every constant sits
in [`swish/model/params.py`](swish/model/params.py) with its source. Full
write-up: [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) ·
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
[`docs/DATA.md`](docs/DATA.md).

## Tech

- **Python 3.10+** · **FastAPI** + **Uvicorn** · **Typer** CLI · **NumPy** for the model
- Scraper: **httpx** + **BeautifulSoup**/**lxml**, rate-limited, with a SQLite response cache
- Frontend: **vanilla ES modules**, no build step, SVG charts written by hand ([`swish/web/charts.js`](swish/web/charts.js))
- Tooling: **ruff**, **mypy** (strict on the model core), **pytest** + **Hypothesis**, **GitHub Actions**

## Testing

```bash
pytest                 # ~60 tests, ~12s, fully offline
pytest --cov=swish
ruff check swish tests && ruff format --check swish tests
mypy swish
```

The suite runs against recorded Basketball-Reference HTML in
[`tests/fixtures/`](tests/fixtures/) — the scraper's network call is the only
thing stubbed, so the parsers and model are exercised against real pages. The
model has property tests (Hypothesis): more WAR ⇒ more value, younger ⇒ more
value at equal production, higher salary ⇒ less surplus, `p10 ≤ p50 ≤ p90`.

## Known limitations

- **One blended box-score metric.** VORP and Win Shares are box-score-derived;
  they underrate high-usage shot creators. Banchero is the clearest current case.
- **The aging curve is a population average.** Individual players age faster or
  slower than the curve; the model doesn't know which.
- **Options are treated as guaranteed.** A player/team option year is counted at
  face value and flagged, not modelled.
- **It needs recent NBA minutes.** Rookies with no NBA season and players years
  removed from the league get a "not enough data" error.
- **Basketball-Reference is the single source.** If they're down and the page
  isn't cached, the lookup fails.

## Roadmap

- [ ] Fit the aging curve from the historical data in the cache (`swish calibrate`)
- [ ] Play-by-play / tracking metrics to temper the box-score blind spots
- [ ] Model player and team options as decisions, not guarantees
- [ ] Cap-sheet awareness in the trade calculator (salary matching)
- [ ] Historical "what was he worth *then*" mode

## The name

A shot that goes straight through without touching the rim. The goal here is the
same: a clean number, and you can see exactly how it got there.

## License

MIT — see [LICENSE](LICENSE). Not affiliated with the NBA or Sports Reference.
Player data © Sports Reference LLC; see [`docs/DATA.md`](docs/DATA.md).
