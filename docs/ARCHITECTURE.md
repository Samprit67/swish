# Architecture

```
                     basketball-reference.com
                              |
  swish/data/  (the scraper)  |
      fetch.py   rate-limited httpx, retries, honours Retry-After
      cache.py   SQLite response cache, keyed by URL
      bref.py    URL builders, season arithmetic, name resolution
      parse.py   HTML  ->  typed dataclasses
      repo.py    the one class the rest of the app calls
                              |
                   PlayerCard, SeasonContext   (schema.py)
                              |
  swish/model/  (pure functions, numpy only)
      params.py  ->  production.py  ->  aging.py  ->  value.py
                            \-> percentiles.py    \-> simulate.py
      pipeline.evaluate()   ->   Valuation
                              |
        +---------------------+---------------------+
        |                                          |
  swish/api/  (FastAPI)                       swish/cli.py  (Typer + rich)
      present.py serializes a Valuation           reuses present.py
        |
  swish/web/  vanilla ES modules, hand-drawn SVG, no build step
```

## The three layers

**`swish/data/` gets data in.** It knows about HTTP, HTML, and
Basketball-Reference's quirks, and nothing about trade value. Its output is two
typed shapes in [`schema.py`](../swish/data/schema.py):

- `PlayerCard`: bio, every NBA regular season (per-game and advanced merged),
  the guaranteed contract, and salary history.
- `SeasonContext`: one season of league-wide advanced stats, used for ranking.

`Repo` is the only class the rest of the app touches, with three methods:
`resolve(name)`, `player_card(ref)`, `season_context(year)`.
`Fetcher._download` is the single network seam, and the tests subclass it to
read fixtures.

**`swish/model/` does the calculation.** Every function is pure and typed, takes
plain dataclasses and a `Params`, and returns dataclasses. No I/O, no globals.
That is what makes the test suite fast and the logic auditable.
`pipeline.evaluate()` composes the steps into a `Valuation` that carries every
intermediate value, not just the headline. See
[`METHODOLOGY.md`](METHODOLOGY.md).

**`swish/api/`, `swish/cli.py`, and `swish/web/` present it.**
[`present.py`](../swish/api/present.py) turns a `Valuation` into a plain dict.
The API returns that as JSON and the CLI renders it as tables, both from the
same serializer. The frontend is static files: no bundler, no framework, SVG
charts written by hand in [`charts.js`](../swish/web/charts.js).

## Why it's shaped this way

- A **pure model core** makes property-based testing trivial and the numbers
  reproducible (the RNG seed is fixed).
- A **single `Repo` seam** lets the whole suite run offline against about 25
  recorded HTML pages: no network, no flakiness, around 12 seconds.
- **`present.py` shared by the API and the CLI** means the terminal and the
  browser can never drift apart.
- **No build step on the frontend** means you clone the repo, run `swish serve`,
  and you are done. Hand-drawing the charts is a constraint that keeps the
  dependency list honest.

## Request flow: `GET /api/players/{id}/value`

1. `Repo.resolve` fetches the relevant `/players/{letter}/` index pages (cached
   for about 30 days) and matches the name to a player id, falling back to
   Basketball-Reference's own search for first names and nicknames.
2. `Repo.player_card` fetches `/players/{l}/{id}.html` once (cached for about 14
   days) and parses it a single time for bio, seasons, contract, and salary
   history.
3. `Repo.season_context` fetches the two current-season leaderboard pages
   (cached for about a day), shared across every player in the process.
4. `model.evaluate(card, context, params)` runs. It is pure, a few milliseconds
   plus the 5,000-run Monte Carlo.
5. `present.valuation_dict` produces the JSON.

The server warms step 3 in a background thread on startup, and a token-bucket
throttle (a burst of 4, then one request every 3 seconds) lets a cold lookup
fire its remaining requests without waiting. In practice a cold lookup is one to
two seconds, just the player page, and a warm lookup is around 50 milliseconds
with no network at all.
