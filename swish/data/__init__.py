"""Getting NBA data in: a polite cached scraper for Basketball-Reference.

Nothing here knows anything about trade value. This layer's whole job is to turn
``"Luka Doncic"`` into a typed :class:`~swish.data.schema.PlayerCard` and a
:class:`~swish.data.schema.SeasonContext`, fetching from
basketball-reference.com at most once and caching the HTML on disk forever
after.
"""

from swish.data.fetch import Fetcher
from swish.data.repo import Repo
from swish.data.schema import (
    ContractYear,
    LeagueLine,
    PlayerBio,
    PlayerCard,
    PlayerRef,
    SeasonContext,
    SeasonLine,
)

__all__ = [
    "ContractYear",
    "Fetcher",
    "LeagueLine",
    "PlayerBio",
    "PlayerCard",
    "PlayerRef",
    "Repo",
    "SeasonContext",
    "SeasonLine",
]
