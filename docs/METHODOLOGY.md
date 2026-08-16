# Methodology

How Swish turns a stat line into a trade-value number. Every constant named here
lives in [`swish/model/params.py`](../swish/model/params.py); every step is a
function in [`swish/model/`](../swish/model/). Nothing is hidden — the API and
`swish value --json` return every intermediate quantity.

The worked examples use the 2025-26 season.

---

## 1 · Production → wins  (`production.py`)

Two public metrics already try to answer "how many wins was this player worth?":

- **VORP** — value over replacement player, a box-score plus-minus estimate
  prorated to a full season.
- **Win Shares (WS)** — box-score credit for a team's wins, split offense/defense.

We convert each to **wins above replacement (WAR)** and blend:

```
war_vorp = VORP × 1.9
war_ws   = WS − 0.055 × (minutes / 48)
war      = 0.60 · war_vorp + 0.40 · war_ws  + creation_bump
```

- **Why 1.9, not Basketball-Reference's 2.7?** BR's own conversion implies
  ~26-WAR MVP seasons. Every published all-in-one metric (RAPTOR, EPM, LEBRON)
  puts peak seasons at 13–18. The factor is calibrated so the top of the league
  lands in that range.
- **Why subtract 0.055 WS/48, not 0.100?** `.100` WS/48 is *league average*, not
  replacement. A freely available replacement plays around `.055`. Subtracting
  average would make every role player negative.
- **`creation_bump`** — `0.055 × max(0, usage% − 24) × min(1, minutes/2000)`.
  Box-score metrics systematically underrate players who create a lot of offense
  on the ball; this claws a little of that back. It is small on purpose.

_2025-26 examples:_ Jokić ≈ 19 · Gilgeous-Alexander ≈ 14 · Banchero ≈ 3.3 ·
a rotation wing ≈ 1–2 · replacement ≈ 0.

## 2 · True talent  (`production.py`)

A single season is noisy. Each of the **last three seasons** is regressed toward
the player's **own trailing form** — the minutes-weighted mean of the two
seasons before it — not toward a generic replacement level:

```
w        = minutes / (minutes + 260)
baseline = 0.85 · (trailing 2-season mean)  +  0.15 · league_prior(0.6)
season_talent = w · war  +  (1 − w) · baseline
```

Then blend the three shrunk seasons, weighting recent and higher-minute seasons
more (`weight = 0.5^k · min(minutes, 2600)`, `k` = seasons back).

Regressing toward the player's own history is what keeps a 22-year-old who just
made a leap from being dragged to the league mean, and an injury-shortened
season for a veteran from being propped up by what he did five years ago.

## 3 · Age curve  (`aging.py`)

Production is aged forward with a per-year multiplier. A player at age *a* gets
the product of the factors from *a+1* onward:

| age → | 21 | 24 | 27 | 30 | 33 | 36 | 39 |
|---|---|---|---|---|---|---|---|
| year factor | +5.0% | +2.0% | 0% | −4.0% | −11% | −20% | −30% |

Peak at 27, gentle rise before, accelerating decline after — the shape of the
publicly replicated NBA aging curves. Season *t* of the projection is
`talent × Π factors × availability`.

**Availability** is the share of 82 games expected:
`0.90 − 0.012 per year over 30`, blended 50/50 with the player's own recent
games-played rate, clamped to `[0.30, 0.97]`.

## 4 · Dollars  (`value.py`)

```
price_per_win(t) = $3.3M × 1.07^t                 # cap grows ~7%/yr
discount(t)      = 1 / 1.08^t                      # a win now > a win in 3 yrs
star_mult(war)   = min(2.7, 1 + 0.12 · max(0, war − 2))
production_value = Σ_t  war_t · price_per_win(t) · star_mult(war_t) · discount(t)
```

**The star premium** is the one non-obvious piece. Wins concentrated on one
roster spot are worth more than the same wins spread across three role players —
a contender can't assemble an 14-win player out of three 4-win players (roster
spots, diminishing returns, the value of actually contending). So the marginal
price of a win rises with the player's level, capped at 2.7×.

- `$3.3M / win` — public "cost of a win" estimates cluster around $3.0–3.6M.
- `8%` discount, `7%` cap growth — round, adjustable in the UI.

## 5 · Contract → surplus  (`value.py`)

```
surplus = production_value − Σ_t discount(t) · salary_t
```

Guaranteed salary comes straight off the player's Basketball-Reference page.
Basketball-Reference also appends a *projected* rookie-scale extension for young
players with no marker; Swish detects that (a >55% year-over-year jump for a
player still on a rookie deal) and drops it.

For horizon years **past** the guaranteed contract, the player is assumed to
re-sign at `min(max_salary, war × $3.3M)` — the open market pays roughly the
base rate per win with no star premium, and that underpayment of stars is
exactly where a superstar's surplus comes from.

With `use_contract = false` the headline is production value and this whole step
is skipped.

## 6 · Draft-pick equivalence  (`value.py`)

A smooth pick-value curve, `value(pick) = $56M · e^(−0.075·(pick−1))`, fit
through public Pelton-style pick charts (#1 ≈ $56M of surplus, tailing to a few
million by the end of the draft). The surplus is inverted onto it:

```
$40M surplus  →  "a lottery pick (~#6)"
$8M  surplus  →  "a first-round pick (~#22)"
−$10M         →  "negative — the contract outweighs the production"
$120M         →  "the #1 pick plus 2 quality starters"
```

## 7 · Uncertainty  (`simulate.py`)

A vectorised Monte Carlo, `n_sims = 5000`, resamples:

| source | distribution |
|---|---|
| true talent | Normal, σ scales with `1/confidence` and with youth (more for players under 25) |
| aging | a compounding ±3% wobble per projected year |
| availability | ±6% per year |
| $ / win | ±10% |

The 10th / 50th / 90th percentiles of the resulting surplus are the reported
band; the per-year WAR percentiles drive the projection fan chart; a 32-bin
histogram drives the distribution strip.

## Percentile context  (`percentiles.py`)

Not part of the value calculation — the radar/bar context. The player's
per-game and advanced numbers are ranked against every rotation player
(≥ 800 minutes) in the same season: scoring, playmaking, rebounding, defense
(STL+BLK), efficiency (TS%), usage, box plus-minus.

## Things this model gets wrong

- **High-usage scorers** (Banchero, sometimes Mitchell) — box metrics don't see
  their creation value; the `creation_bump` is a patch, not a fix.
- **Elite defenders on low-usage offenses** can be underrated the other way.
- **Very young stars** (Wembanyama) — the model rewards realized production, so
  it will sit below consensus on players whose value is mostly ceiling.
- **Options** are counted as guaranteed and only flagged.
- **Team fit / positional scarcity / playoff record** — not modelled at all.
