# Architecture

```
                    basketball-reference.com
                             │
        ┌────────────────────┴─────────────────────┐
        │  swish/data/                             │
        │  ┌───────────┐  ┌──────────┐  ┌────────┐ │
        │  │ fetch.py  │→ │ cache.py │  │bref.py │ │  rate-limited httpx,
        │  │ (throttle,│  │ (SQLite  │  │(urls,  │ │  SQLite response cache,
        │  │  retry)   │  │  by url) │  │ names) │ │  name → player-id
        │  └───────────┘  └──────────┘  └────────┘ │
        │        └────────► parse.py ◄─────────┐   │  HTML → dataclasses
        │                     │                │   │
        │                repo.py  ─────────────┘   │  the one class callers use
        └────────────────────┬─────────────────────┘
                             │  PlayerCard, SeasonContext   (schema.py)
        ┌────────────────────┴─────────────────────┐
        │  swish/model/            (pure functions, numpy only)
        │  params.py → production.py → aging.py → value.py
        │                    ↘ percentiles.py   ↘ simulate.py
        │                        pipeline.evaluate()  →  Valuation
        └────────────────────┬─────────────────────┘
                             │
        ┌──────────┴───────────┐        ┌──────────┴──────────┐
        │  swish/api/          │        │  swish/cli.py       │
        │  FastAPI, present.py │        │  Typer + rich       │
        │  serializes Valuation│        │  reuses present.py  │
        └──────────┬───────────┘        └─────────────────────┘
                   │
        swish/web/ — vanilla ES modules, hand-rolled SVG, no build step
```

## The three layers

**`swish/data/` — getting data in.** Knows about HTTP, HTML and
Basketball-Reference's quirks; knows nothing about trade value. Its output is
two typed shapes in [`schema.py`](../swish/data/schema.py):

- `PlayerCard` — bio, every NBA regular season (per-game + advanced merged),
  the guaranteed contract, salary history.
- `SeasonContext` — one season's league-wide advanced stats, for ranking.

`Repo` is the only class the rest of the app touches: `resolve(name)`,
`player_card(ref)`, `season_context(year)`. `Fetcher._download` is the single
network seam — tests subclass it to read fixtures.

**`swish/model/` — the calculation.** Every function is pure and typed, takes
plain dataclasses and a `Params`, returns dataclasses. No I/O, no globals. This
is what makes the test suite fast and the logic auditable. `pipeline.evaluate()`
composes the steps into a `Valuation` that carries *every* intermediate value,
not just the headline. See [`METHODOLOGY.md`](METHODOLOGY.md).

**`swish/api/` + `swish/cli.py` + `swish/web/` — presentation.**
[`present.py`](../swish/api/present.py) turns a `Valuation` into a plain dict;
the API returns it as JSON, the CLI renders it as rich tables, both from the
same serializer. The frontend is static files — no bundler, no framework, SVG
charts written by hand in [`charts.js`](../swish/web/charts.js).

## Why it's shaped this way

- **Pure model core** → property-based testing is trivial and the numbers are
  reproducible (fixed RNG seed).
- **One `Repo` seam** → the entire suite runs offline against ~25 recorded HTML
  pages; no network, no flakiness, ~12 seconds.
- **`present.py` shared by API and CLI** → the terminal and the browser can
  never drift.
- **No build step on the frontend** → clone, `swish serve`, done. The charts
  being hand-rolled is a constraint that keeps the dependency list honest.

## Request flow: `GET /api/players/{id}/value`

1. `Repo.resolve` — fetch the relevant `/players/{letter}/` index page(s) (cached
   ~30 days), fuzzy-match the name to a player id.
2. `Repo.player_card` — fetch `/players/{l}/{id}.html` once (cached ~14 days),
   parse the soup a single time for bio + seasons + contract + salary history.
3. `Repo.season_context` — fetch the two current-season leaderboard pages
   (cached ~24h), shared across every player in the process.
4. `model.evaluate(card, context, params)` — pure, ~a few ms plus the 5,000-run
   Monte Carlo.
5. `present.valuation_dict` → JSON.

The server warms step 3 in a background thread on startup, and a token-bucket
throttle (burst of 4, then one request per 3s sustained) lets a cold lookup
fire its remaining requests without waiting. So in practice: **cold ≈ 1–2s**
(just the player page), **warm ≈ 50ms** (no network at all).
