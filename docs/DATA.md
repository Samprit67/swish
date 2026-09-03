# Data

Swish reads from **basketball-reference.com**. Two things sit in front of that:

1. A **committed season snapshot** ([`swish/data/season.json`](../swish/data/season.json)),
   rebuilt with `swish data build`. It holds this season's top ~320 players by
   minutes (career tables, contract, salary history) plus the league context,
   already parsed. The app reads it before anything else, so a fresh clone or a
   cold deploy answers common lookups with no network at all.
2. A **local SQLite cache** of every page fetched live, for everyone outside the
   snapshot.

## The season snapshot

`swish data build` walks the current season's advanced leaderboard, takes the
top N players by minutes (320 by default, `--top` to change), fetches each
player page once through the normal rate-limited path, and writes the parsed
`Snapshot` to `swish/data/season.json` (about 1 MB, one compact line, like a
lockfile). Re-runs reuse the cache, so a rebuild after a few new games is cheap.

`swish data info` prints the season, player count, and build date.
`load_snapshot()` in [`snapshot.py`](../swish/data/snapshot.py) is what the app
calls on start; a missing or unparseable file just means "fall back to live".

It is a point-in-time copy: numbers freeze at build time. Rerun `swish data
build` when the season moves on (the committed file's `built_at` says how old it
is).

## Pages used

| purpose | URL | cache lifetime |
|---|---|---|
| name to player id | `/players/{letter}/` and `/search/search.fcgi` | 30 days |
| career and contract | `/players/{l}/{id}.html` | 14 days |
| league context and leaderboard | `/leagues/NBA_{year}_advanced.html` and `_per_game.html` | 24 hours |

The player page is a single request that carries everything Swish needs:
per-game and advanced career tables (each cell has a `data-stat` attribute, so
parsing survives a column reshuffle), salary history, and the guaranteed
contract. Some of those tables are delivered inside an HTML comment, and
[`parse.py`](../swish/data/parse.py) splices them back in.

## Being a good citizen

From [`fetch.py`](../swish/data/fetch.py):

- A **token bucket**. A short burst is allowed, so one cold player lookup fires
  its three or four requests back to back, but the sustained rate holds at one
  request every 3 seconds (`SWISH_MIN_INTERVAL` and `SWISH_BURST` change this).
  That is well under the roughly 20 per minute that Sports Reference asks
  crawlers to stay below.
- A descriptive `User-Agent` that identifies the tool.
- It honours `Retry-After` on a 429 and backs off exponentially on a 5xx.
- Every response is cached in SQLite, so repeat runs make zero requests. A cold
  single-player lookup is three or four requests, and everything after that is
  served from disk.
- `swish data build` is the one job that fetches in bulk: ~320 player pages, one
  every 3 seconds, about eight minutes. It is run by hand, occasionally, not on
  a schedule.

Analysing one player and browsing his dashboard is a handful of requests. The
leaderboard is two. This is within reasonable personal use, but it is still
scraping, so read
[Sports Reference's terms](https://www.sports-reference.com/termsofuse.html) and
do not point it at a loop.

## The cache

SQLite, one table (`url -> body, status, fetched_at`), stored at:

- macOS: `~/Library/Application Support/swish/cache.db`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/swish/cache.db`
- override: `SWISH_CACHE=/path/to/cache.db`

```bash
swish cache info      # pages, size, age
swish cache clear     # forget everything
SWISH_OFFLINE=1 swish value "Nikola Jokic"   # cache only, never touch the network
```

## Test fixtures

[`tests/fixtures/`](../tests/fixtures/) holds around 25 real Basketball-Reference
pages, gzipped, captured once. The test suite serves these instead of hitting
the network (`FixtureFetcher` in `conftest.py` overrides `Fetcher._download`),
so the parsers and the model run against genuine HTML with no flakiness. They
are test infrastructure: raw pages the parsers turn into dataclasses, separate
from the committed `season.json` the running app reads.

To refresh them, re-run the capture with a live network connection. The URL map
is in the docstring at the top of `tests/conftest.py`.

## Licensing

Player statistics and salary data are copyright Sports Reference LLC. Swish is an
independent project, not affiliated with or endorsed by Sports Reference or the
NBA.

The code is MIT licensed. The data is not Swish's to relicense.
`swish/data/season.json` is a small derived subset (about 320 players' parsed
career and contract lines) checked in so the demo runs offline; it is credited
here and to be treated as Sports Reference's, not redistributed as a dataset.
Delete it and the app rebuilds it live.
