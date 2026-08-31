# Methodology

How Swish turns a stat line into a trade-value number. Every constant named
here lives in [`swish/model/params.py`](../swish/model/params.py), and every
step is a function in [`swish/model/`](../swish/model/). Nothing is hidden: the
API and `swish value --json` return every intermediate quantity.

The worked examples use the 2025-26 season.

## 1. Production to wins (`production.py`)

Two public metrics already try to answer "how many wins was this player worth?":

- **VORP**, value over replacement player, a box-score plus-minus estimate
  prorated to a full season.
- **Win Shares (WS)**, box-score credit for a team's wins, split into an
  offensive and a defensive part.

Swish converts each one to **wins above replacement (WAR)** and blends them:

```
war_vorp = VORP * 1.9
war_ws   = WS - 0.055 * (minutes / 48)
war      = 0.60 * war_vorp + 0.40 * war_ws + creation_bump
```

- **Why 1.9, not Basketball-Reference's 2.7?** Their own conversion implies
  26-WAR MVP seasons. Every published all-in-one metric (RAPTOR, EPM, LEBRON)
  puts peak seasons at 13 to 18. The factor is calibrated so the top of the
  league lands in that range.
- **Why subtract 0.055 WS/48, not 0.100?** A WS/48 of .100 is *league average*,
  not replacement level. A freely available replacement plays around .055.
  Subtracting the average would make every role player look negative.
- **`creation_bump`** is `0.055 * max(0, usage% - 24) * min(1, minutes/2000)`.
  Box-score metrics systematically underrate players who create a lot of
  offense on the ball, and this claws a little of that back. It is small on
  purpose.

2025-26 examples: Jokić about 19, Gilgeous-Alexander about 14, Banchero about
3.3, a rotation wing 1 to 2, a replacement player 0.

## 2. True talent (`production.py`)

A single season is noisy. Each of the **last three seasons** is regressed toward
the player's **own trailing form**, meaning the minutes-weighted mean of the two
seasons before it, rather than toward a generic replacement level:

```
w        = minutes / (minutes + 260)
baseline = 0.85 * (trailing 2-season mean) + 0.15 * league_prior(0.6)
season_talent = w * war + (1 - w) * baseline
```

The three shrunk seasons are then blended, weighting recent, higher-minute
seasons more (`weight = 0.5^k * min(minutes, 2600)`, where `k` is how many
seasons back).

Regressing toward the player's own history is what keeps a 22-year-old who just
made a leap from being dragged back to the league mean, and stops an
injury-shortened veteran season from being propped up by what he did five years
ago.

## 3. Age curve (`aging.py`)

Production is aged forward with a per-year multiplier. A player at age `a` gets
the product of the factors from `a + 1` onward:

| age | 21 | 24 | 27 | 30 | 33 | 36 | 39 |
|---|---|---|---|---|---|---|---|
| year factor | +5.0% | +2.0% | 0% | -4.0% | -11% | -20% | -30% |

The shape (a peak at 27, a gentle rise before it, an accelerating decline after)
follows the publicly replicated NBA aging curves. Season `t` of the projection
is `talent * (product of factors) * availability`.

**Availability** is the share of 82 games expected: `0.90 - 0.012 for every year
over 30`, blended 50/50 with the player's own recent games-played rate, and
clamped to the range 0.30 to 0.97.

## 4. Dollars (`value.py`)

```
price_per_win(t) = $3.3M * 1.07^t              # the cap grows ~7% a year
discount(t)      = 1 / 1.08^t                  # a win now beats a win in 3 years
star_mult(war)   = min(2.7, 1 + 0.12 * max(0, war - 2))
production_value = sum over t of
                   war_t * price_per_win(t) * star_mult(war_t) * discount(t)
```

**The star premium** is the one non-obvious piece. Wins concentrated on one
roster spot are worth more than the same number of wins spread across three role
players. A contender cannot assemble a 14-win player out of three 4-win players
(roster spots, diminishing returns, the value of actually contending). So the
marginal price of a win rises with the player's level, capped at 2.7 times.

- The `$3.3M per win` figure sits in the middle of public "cost of a win"
  estimates, which cluster around $3.0M to $3.6M.
- The 8% discount and 7% cap growth are round numbers, both adjustable in the UI.

## 5. Contract to surplus (`value.py`)

```
surplus = production_value - sum over t of discount(t) * salary_t
```

Guaranteed salary comes straight off the player's Basketball-Reference page.
The site also appends a *projected* rookie-scale extension for young players,
with no marker to distinguish it. Swish detects that (a jump of more than 55%
year over year for a player still on a rookie deal) and drops it.

For horizon years **past** the guaranteed contract, the player is assumed to
re-sign at `min(max_salary, war * $3.3M)`. The open market pays roughly the base
rate per win with no star premium, and that underpayment of stars is exactly
where a superstar's surplus comes from.

With `use_contract = false` the headline becomes production value and this whole
step is skipped.

## 6. Draft-pick equivalence (`value.py`)

A smooth pick-value curve, `value(pick) = $56M * e^(-0.075 * (pick - 1))`, fit
through public Pelton-style pick charts (the number one pick is worth about
$56M of surplus, tailing to a few million by the end of the draft). The surplus
is inverted onto that curve:

```
$40M surplus  ->  "a lottery pick (~#6)"
$8M  surplus  ->  "a first-round pick (~#22)"
-$10M         ->  "negative, the contract outweighs the production"
$120M         ->  "the #1 pick plus 2 quality starters"
```

## 7. Uncertainty (`simulate.py`)

A vectorised Monte Carlo, `n_sims = 5000`, resamples four inputs:

| source | distribution |
|---|---|
| true talent | Normal; the spread scales with `1 / confidence` and with youth (wider for players under 25) |
| aging | a compounding wobble of plus or minus 3% per projected year |
| availability | plus or minus 6% per year |
| cost per win | plus or minus 10% |

The 10th, 50th, and 90th percentiles of the resulting surplus are the reported
band. The per-year WAR percentiles drive the projection fan chart, and a 32-bin
histogram drives the distribution strip under the headline number.

## Percentile context (`percentiles.py`)

Not part of the value calculation, this is the context for the radar and bar
charts. The player's per-game and advanced numbers are ranked against every
rotation player (800 minutes or more) in the same season, across scoring,
playmaking, rebounding, defense (steals plus blocks), efficiency (true shooting
percentage), usage, and box plus-minus.

## Things this model gets wrong

- **High-usage scorers** like Banchero, and sometimes Mitchell. Box metrics
  don't see their creation value, and the `creation_bump` is a patch, not a fix.
- **Elite defenders on low-usage offenses** can be underrated the other way.
- **Very young stars** like Wembanyama. The model rewards realized production,
  so it sits below consensus on players whose value is mostly ceiling.
- **Options** are counted as guaranteed and only flagged.
- **Team fit, positional scarcity, and playoff record** are not modelled at all.
