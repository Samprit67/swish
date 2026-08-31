# Data

Swish reads from **basketball-reference.com**. It stores no dataset of its own.
Every page is fetched on demand and cached locally.

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

Analysing one player and browsing his dashboard is a handful of requests. The
leaderboard is two. This is well within reasonable personal use, but it is still
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
are test infrastructure, not a shipped dataset. The application itself always
fetches live.

To refresh them, re-run the capture with a live network connection. The URL map
is in the docstring at the top of `tests/conftest.py`.

## Licensing

Player statistics and salary data are copyright Sports Reference LLC. Swish is an
independent tool, not affiliated with or endorsed by Sports Reference or the
NBA. The code is MIT licensed; the data it fetches is not Swish's to relicense.
