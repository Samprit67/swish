# Contributing

Thanks for taking a look.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install        # optional, runs ruff on commit
```

## Before you push

```bash
make check                # ruff, mypy, and pytest, the same as CI
```

## Conventions

- **The model core is pure.** Functions in `swish/model/` take dataclasses and a
  `Params` and return dataclasses. No I/O, no globals, no reading the clock.
  That is what makes them testable and the numbers reproducible.
- **Every model constant lives in `params.py`**, with a comment saying where it
  came from. If you are hard-coding a number in `production.py` or `value.py`,
  move it.
- **New behaviour needs a test.** Model changes need a *property* test where one
  makes sense: monotonicity, bounds, ordering.
- **Tests stay offline.** If you need a Basketball-Reference page the fixtures
  don't have, capture it into `tests/fixtures/` and add it to the route map in
  `conftest.py`. Don't reach for the network.
- **User-facing failures** subclass `swish.errors.SwishError`. Anything else is a
  bug and should crash loudly.
- Line length is 108. `ruff format` is the source of truth for style.

## Good first issues

- Fit the aging curve from the seasons already in the cache (`swish calibrate`)
  and compare it to the hand-set one in `params.py`.
- Add a play-by-play or tracking metric to the WAR blend to temper the
  box-score blind spot on shot creators.
- Model player and team options as decisions instead of counting them as
  guaranteed.
- Salary-matching rules in the trade calculator.
