"""Errors that are meant to be shown to a person, not logged as a bug."""

from __future__ import annotations


class SwishError(Exception):
    """Base class for expected, user-facing failures."""


class PlayerNotFound(SwishError):
    """No Basketball-Reference player matched the search string.

    Carries the near-misses so the caller can say "did you mean …?".
    """

    def __init__(self, query: str, *, suggestions: list[str] | None = None):
        self.query = query
        self.suggestions = suggestions or []
        hint = f" Did you mean: {', '.join(self.suggestions)}?" if self.suggestions else ""
        super().__init__(f"No NBA player found for {query!r}.{hint}")


class NotEnoughData(SwishError):
    """A player was found but has too little recent NBA play to value."""


class SourceUnavailable(SwishError):
    """Basketball-Reference could not be reached and nothing usable was cached.

    ``retry_after`` is set when the site told us to back off.
    """

    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after
