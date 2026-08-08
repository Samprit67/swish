"""Where a player ranks in the league — the context for the charts.

Not part of the value calculation; this is what powers the percentile bars and
the radar. Percentiles are taken against rotation players (a minutes floor) so
a deep-bench player posting gaudy per-minute numbers doesn't set the scale.
"""

from __future__ import annotations

from dataclasses import dataclass

from swish.data.schema import LeagueLine, SeasonContext, SeasonLine

_MIN_MINUTES = 800


@dataclass(frozen=True)
class Percentile:
    key: str
    label: str
    value: float
    percentile: float  # 0..100
    league_median: float


def _pct(value: float, population: list[float]) -> float:
    if not population:
        return 50.0
    below = sum(1 for x in population if x < value)
    equal = sum(1 for x in population if x == value)
    return 100.0 * (below + 0.5 * equal) / len(population)


def _median(population: list[float]) -> float:
    if not population:
        return 0.0
    s = sorted(population)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else 0.5 * (s[mid - 1] + s[mid])


_FIELDS: list[tuple[str, str]] = [
    ("pts", "Scoring"),
    ("ast", "Playmaking"),
    ("trb", "Rebounding"),
    ("stocks", "Defense (STL+BLK)"),
    ("ts_pct", "Efficiency (TS%)"),
    ("usg_pct", "Usage"),
    ("bpm", "Box +/-"),
]


def _value(obj: LeagueLine | SeasonLine, key: str) -> float:
    if key == "stocks":
        return obj.stl + obj.blk
    return float(getattr(obj, key))


def player_percentiles(line: SeasonLine, context: SeasonContext) -> list[Percentile]:
    pool = [ln for ln in context.lines if ln.minutes >= _MIN_MINUTES]
    out: list[Percentile] = []
    for key, label in _FIELDS:
        population = [_value(ln, key) for ln in pool]
        value = _value(line, key)
        out.append(
            Percentile(
                key=key,
                label=label,
                value=value,
                percentile=round(_pct(value, population), 1),
                league_median=round(_median(population), 3),
            )
        )
    return out
