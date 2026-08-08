"""The trade-value model.

Given a player's career (:class:`~swish.data.schema.PlayerCard`) and a season of
league context, produce a :class:`~swish.model.pipeline.Valuation`: what the
player is worth as a trade asset, why, and how uncertain that is.

Every step is a pure function over plain dataclasses. Every knob lives in
:mod:`swish.model.params` with a source. The write-up is ``docs/METHODOLOGY.md``.
"""

from swish.model.params import Params
from swish.model.pipeline import Valuation, evaluate

__all__ = ["Params", "Valuation", "evaluate"]
