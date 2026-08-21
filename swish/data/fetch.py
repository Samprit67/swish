"""The polite fetcher.

Rules it follows so Basketball-Reference keeps letting us in:

* a **token bucket** — a short burst is allowed (so one cold player lookup fires
  its 3-4 requests back to back) but the sustained rate stays at one request
  every ``settings.min_interval`` seconds,
* honour ``Retry-After`` on 429s,
* back off exponentially on 5xx,
* and once a page is cached, never ask for it again until it goes stale.

``_download`` is the single network seam — tests subclass and override it.
"""

from __future__ import annotations

import base64
import threading
import time

import httpx

from swish.config import Settings
from swish.data.cache import Cache
from swish.errors import SourceUnavailable

BASE_URL = "https://www.basketball-reference.com"

# how long a cached page stays fresh, by kind of page
MAX_AGE_PLAYER = 14 * 24 * 3600.0
MAX_AGE_SEASON = 24 * 3600.0
MAX_AGE_INDEX = 30 * 24 * 3600.0

_MAX_TRIES = 4


class Fetcher:
    def __init__(self, cache: Cache, settings: Settings | None = None):
        self.cache = cache
        self.settings = settings or Settings()
        self._lock = threading.Lock()
        self._tokens = float(self.settings.burst)
        self._refilled_at = time.monotonic()

    # -- public ------------------------------------------------------------

    def get(self, path: str, *, max_age: float) -> str:
        """Return the body of ``BASE_URL + path``, from cache when it can."""
        url = path if path.startswith("http") else BASE_URL + path
        cached = self.cache.get(url)
        if cached is not None and cached.status == 200 and cached.age() <= max_age:
            return cached.body

        if self.settings.offline:
            if cached is not None and cached.status == 200:
                return cached.body
            raise SourceUnavailable(
                f"Offline and {url} is not cached. Run without SWISH_OFFLINE once to warm the cache."
            )

        try:
            body = self._download(url)
        except SourceUnavailable:
            if cached is not None and cached.status == 200:
                return cached.body  # stale is better than nothing
            raise
        self.cache.put(url, body, 200)
        return body

    def get_image(self, path: str, *, max_age: float) -> bytes | None:
        """Fetch a (cached) image; ``None`` if it doesn't exist or can't be reached.

        Stored base64 in the same cache; a miss is remembered as a 404 so we
        don't re-ask for a headshot the player doesn't have.
        """
        url = path if path.startswith("http") else BASE_URL + path
        key = "img:" + url
        cached = self.cache.get(key)
        if cached is not None and cached.age() <= max_age:
            return base64.b64decode(cached.body) if cached.status == 200 and cached.body else None
        if self.settings.offline:
            if cached is not None and cached.status == 200 and cached.body:
                return base64.b64decode(cached.body)
            return None
        try:
            self._throttle()
            resp = httpx.get(
                url,
                headers={"User-Agent": self.settings.user_agent},
                timeout=15.0,
                follow_redirects=True,
            )
        except httpx.HTTPError:
            return None
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
            self.cache.put(key, base64.b64encode(resp.content).decode(), 200)
            return resp.content
        self.cache.put(key, "", 404)
        return None

    # -- network seam ----------------------------------------------------

    def _download(self, url: str) -> str:
        headers = {
            "User-Agent": self.settings.user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        delay = 2.0
        for attempt in range(1, _MAX_TRIES + 1):
            self._throttle()
            try:
                resp = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
            except httpx.HTTPError as exc:
                if attempt == _MAX_TRIES:
                    raise SourceUnavailable(f"Could not reach {url}: {exc}") from exc
                time.sleep(delay)
                delay *= 2
                continue

            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 404:
                raise SourceUnavailable(f"{url} does not exist (404).")
            if resp.status_code == 429:
                wait = _retry_after(resp) or delay
                raise SourceUnavailable(
                    f"Basketball-Reference is rate-limiting us (429). Try again in ~{wait:.0f}s.",
                    retry_after=wait,
                )
            if resp.status_code >= 500 and attempt < _MAX_TRIES:
                time.sleep(delay)
                delay *= 2
                continue
            raise SourceUnavailable(f"{url} returned HTTP {resp.status_code}.")
        raise SourceUnavailable(f"Gave up on {url} after {_MAX_TRIES} tries.")

    # -- internals -----------------------------------------------------

    def _throttle(self) -> None:
        """Token bucket: burst up to ``settings.burst``, refill 1 per interval."""
        interval = self.settings.min_interval
        if interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            self._tokens = min(
                float(self.settings.burst),
                self._tokens + (now - self._refilled_at) / interval,
            )
            self._refilled_at = now
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) * interval
                time.sleep(wait)
                self._tokens = 0.0
                self._refilled_at = time.monotonic()
            else:
                self._tokens -= 1.0


def _retry_after(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
