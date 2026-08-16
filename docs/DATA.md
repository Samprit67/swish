# Data

Swish reads from **basketball-reference.com**. It stores no dataset of its own —
every page is fetched on demand and cached locally.

## Pages used

| purpose | URL | cache TTL |
|---|---|---|
| name → player id | `/players/{letter}/` | 30 days |
| career + contract | `/players/{l}/{id}.html` | 14 days |
| league context, leaderboard | `/leagues/NBA_{year}_advanced.html`, `_per_game.html` | 24 hours |

The player page is a single request that carries everything Swish needs:
per-game and advanced career tables (`data-stat` attributes, so parsing survives
column changes), salary history, and the guaranteed contract (delivered inside
an HTML comment — [`parse.py`](../swish/data/parse.py) splices those back in).

## Being a good citizen

[`fetch.py`](../swish/data/fetch.py):

- **≥ 3.5 seconds between requests** (`SWISH_MIN_INTERVAL` to change), well under
  the ~20/minute Sports Reference asks crawlers to stay below.
- A descriptive `User-Agent` that identifies the tool.
- Honours `Retry-After` on 429s; exponential backoff on 5xx.
- Every response cached in SQLite, so re-runs make **zero** requests. A cold
  single-player lookup is 3 requests; everything after is served from disk.

Analysing one player and browsing his dashboard is a handful of requests. The
leaderboard is 2. This is well within reasonable personal use — but it is
scraping, so read [Sports Reference's terms](https://www.sports-reference.com/termsofuse.html)
and don't point it at a loop.

## The cache

SQLite, one table (`url → body, status, fetched_at`), at:

- macOS: `~/Library/Application Support/swish/cache.db`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/swish/cache.db`
- override: `SWISH_CACHE=/path/to/cache.db`

```bash
swish cache info      # pages, size, age
swish cache clear     # forget everything
SWISH_OFFLINE=1 swish value "Nikola Jokic"   # cache only, never touch the network
```

## Test fixtures

[`tests/fixtures/`](../tests/fixtures/) holds ~25 real Basketball-Reference pages,
gzipped, captured once. The test suite serves these instead of hitting the
network (`FixtureFetcher` in `conftest.py` overrides `Fetcher._download`), so
the parsers and model run against genuine HTML with no flakiness. They are test
infrastructure, not a shipped dataset — the application always fetches live.

To refresh them, re-run the capture with a real network connection (see the
docstring in `tests/conftest.py` for the URL map).

## Licensing

Player statistics and salary data are © Sports Reference LLC. Swish is an
independent tool, not affiliated with or endorsed by Sports Reference or the
NBA. The code is MIT-licensed; the data it fetches is not Swish's to relicense.
