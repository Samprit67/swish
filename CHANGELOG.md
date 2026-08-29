# Changelog

All notable changes to Swish. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

## [0.4.0] — 2026-08-27

### Added
- Player-search dropdowns on the compare and trade inputs; name resolution
  falls back to Basketball-Reference's search so first names / nicknames work.
- Player **headshots** in the hero (proxied from Basketball-Reference, cached,
  initials fallback).
- Skill-percentile **radar chart** on the compare view.
- Chart interactions: draw-in animation, hover crosshair with a readout.
- Skeleton loading states; optimistic player header from the search result.

### Changed
- Cold player lookup is now **~1s** instead of ~10s: a token-bucket throttle
  (burst of 4, then 3s sustained), the current-season leaderboard is warmed in
  a background thread on startup, and the two season pages are fetched
  concurrently.
- Redesigned the whole dashboard — spacing, type, colour, dark mode, the
  value waterfall now interleaves production and salary per season.

## [0.3.0] — 2026-08-16

### Added
- **Web dashboard** (FastAPI + vanilla-JS SPA): player valuation, compare,
  trade calculator, leaderboard, method.
- Hand-rolled SVG charts — line, projection fan chart, value waterfall,
  Monte-Carlo histogram, comparison bars.
- Live analytics controls: horizon, discount rate, $/win, metric
  (VORP / Win Shares / blend), contract on/off.

## [0.2.0] — 2026-08-10

### Added
- **Trade-value model** ([`swish/model/`](swish/model/)): VORP + Win Shares →
  WAR with own-form regression, population age curve, dollar value with a star
  premium, contract surplus, draft-pick-value curve, Monte-Carlo band, league
  percentiles.
- Detection of Basketball-Reference's *projected* rookie-scale extensions so
  they aren't counted as guaranteed salary.
- `swish value / compare / trade / leaderboard / fetch / cache`, all with `--json`.

## [0.1.0] — 2026-08-09

### Added
- Rate-limited, cached Basketball-Reference scraper with a SQLite response cache
  and an offline mode.
- Name resolution (accents, typos, compound surnames, raw ids) against the
  letter-index pages.
- HTML parsers → typed `PlayerCard` / `SeasonContext`.
- Test suite against ~25 recorded HTML fixtures; property tests on the model.
