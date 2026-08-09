"""Build a :class:`~swish.model.Params` from web-friendly query arguments."""

from __future__ import annotations

from swish.model import Params

_METRIC_WEIGHTS = {"vorp": 1.0, "ws": 0.0, "blend": 0.60}


def build_params(
    *,
    horizon: int | None = None,
    discount: float | None = None,
    dollars_per_win: float | None = None,
    metric: str | None = None,
    n_sims: int | None = None,
) -> Params:
    p = Params()
    changes: dict[str, object] = {}
    if horizon is not None:
        changes["horizon"] = max(1, min(5, horizon))
    if discount is not None:
        changes["discount_rate"] = max(0.0, min(0.25, discount))
    if dollars_per_win is not None:
        # accepted in millions from the UI
        value = dollars_per_win * 1_000_000 if dollars_per_win < 1000 else dollars_per_win
        changes["dollars_per_win"] = max(1_000_000.0, min(8_000_000.0, value))
    if metric in _METRIC_WEIGHTS:
        changes["vorp_weight"] = _METRIC_WEIGHTS[metric]
    if n_sims is not None:
        changes["n_sims"] = max(200, min(20000, n_sims))
    return p.with_(**changes) if changes else p
