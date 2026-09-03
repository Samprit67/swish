# Changelog

All notable changes to Swish. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

## [0.5.0] - 2026-09-02

### Added
- A committed **season snapshot** (`swish/data/season.json`): this season's top
  ~320 players by minutes, plus the league context, parsed and stored in the
  repo. A fresh clone or deploy answers common lookups instantly with no
  network. `swish data build` rebuilds it; `swish data info` shows what it holds.

### Changed
- Reworked the front end: a warm paper and charcoal palette on Archivo, a
  player hero that leads with a counting value and a 10th to 90th range bar, and
  a two-column landing page with a hand-drawn shot-arc graphic.
- Static assets are served `no-cache` so a redeploy never leaves a stale bundle
  in the browser.
- The long-tail live lookup is unchanged; only players outside the snapshot
  touch the network now.

## [0.4.0] - 2026-08-27

### Added
- Player-search dropdowns on the compare and trade inputs. Name resolution now
  falls back to Basketball-Reference's own search, so first names and nicknames
  work.
- Player **headshots** in the hero, proxied from Basketball-Reference, cached,
  with an initials fallback.
- A skill-percentile **radar chart** on the compare view.
- Chart interactions: a draw-in animation and a hover crosshair with a readout.
- Skeleton loading states, and an optimistic player header from the search result.

### Changed
- A cold player lookup is now about a second instead of ten. A token-bucket
  throttle allows a burst of 4 requests before the 3-second sustained rate, the
  current-season leaderboard is warmed in a background thread on startup, and the
  two season pages are fetched concurrently.
- Redesigned the whole dashboard: spacing, type, colour, dark mode, and a value
  waterfall that now interleaves production and salary per season.

## [0.3.0] - 2026-08-16

### Added
- A **web dashboard** (FastAPI plus a vanilla-JS SPA): player valuation, compare,
  trade calculator, leaderboard, and method.
- Hand-drawn SVG charts: a line chart, a projection fan chart, a value waterfall,
  a Monte-Carlo histogram, and comparison bars.
- Live analytics controls: horizon, discount rate, cost per win, metric
  (VORP, Win Shares, or a blend), and contract on or off.

## [0.2.0] - 2026-08-10

### Added
- The **trade-value model** ([`swish/model/`](swish/model/)): VORP and Win Shares
  into WAR with own-form regression, a population age curve, a dollar value with a
  star premium, contract surplus, a draft-pick-value curve, a Monte-Carlo band,
  and league percentiles.
- Detection of Basketball-Reference's *projected* rookie-scale extensions, so
  they aren't counted as guaranteed salary.
- `swish value`, `compare`, `trade`, `leaderboard`, `fetch`, and `cache`, all
  with a `--json` flag.

## [0.1.0] - 2026-08-09

### Added
- A rate-limited Basketball-Reference scraper with a SQLite response cache and
  an offline mode.
- Name resolution (accents, typos, compound surnames, raw ids) against the
  letter-index pages.
- HTML parsers that produce typed `PlayerCard` and `SeasonContext` objects.
- A test suite against about 25 recorded HTML fixtures, with property tests on
  the model.
