"""The polite-scraper logic: throttling, retries, 429 handling, offline mode."""

from __future__ import annotations

import httpx
import pytest
from swish.config import Settings, settings_from_env
from swish.data.cache import Cache
from swish.data.fetch import MAX_AGE_SEASON, Fetcher
from swish.errors import SourceUnavailable


def _fetcher(tmp_path, **settings_kw) -> Fetcher:
    return Fetcher(Cache(tmp_path / "c.db"), Settings(min_interval=0.0, **settings_kw))


class _Transport:
    """A fake httpx handler with a scripted sequence of responses."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, request):
        self.calls += 1
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _patch(monkeypatch, transport):
    def fake_get(url, **kw):
        client = httpx.Client(transport=httpx.MockTransport(transport))
        return client.get(url)

    monkeypatch.setattr(httpx, "get", fake_get)


def test_success_is_cached_and_not_refetched(tmp_path, monkeypatch):
    t = _Transport(httpx.Response(200, text="<html>ok</html>"))
    _patch(monkeypatch, t)
    f = _fetcher(tmp_path)
    assert "ok" in f.get("/x.html", max_age=MAX_AGE_SEASON)
    assert "ok" in f.get("/x.html", max_age=MAX_AGE_SEASON)
    assert t.calls == 1


def test_retries_then_succeeds_on_500(tmp_path, monkeypatch):
    t = _Transport(
        httpx.Response(503, text="down"),
        httpx.Response(200, text="<html>back</html>"),
    )
    _patch(monkeypatch, t)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    f = _fetcher(tmp_path)
    assert "back" in f.get("/x.html", max_age=MAX_AGE_SEASON)
    assert t.calls == 2


def test_429_raises_with_retry_after(tmp_path, monkeypatch):
    t = _Transport(httpx.Response(429, headers={"retry-after": "42"}, text="slow down"))
    _patch(monkeypatch, t)
    f = _fetcher(tmp_path)
    with pytest.raises(SourceUnavailable) as exc:
        f.get("/x.html", max_age=MAX_AGE_SEASON)
    assert exc.value.retry_after == 42


def test_stale_cache_is_served_when_the_site_is_down(tmp_path, monkeypatch):
    _patch(monkeypatch, _Transport(httpx.Response(200, text="<html>first</html>")))
    f = _fetcher(tmp_path)
    f.get("/x.html", max_age=MAX_AGE_SEASON)

    _patch(
        monkeypatch,
        _Transport(httpx.Response(503), httpx.Response(503), httpx.Response(503), httpx.Response(503)),
    )
    monkeypatch.setattr("time.sleep", lambda _s: None)
    # max_age 0 forces a refetch; it fails, so the stale copy comes back
    assert "first" in f.get("/x.html", max_age=0)


def test_404_is_a_clean_error(tmp_path, monkeypatch):
    _patch(monkeypatch, _Transport(httpx.Response(404)))
    f = _fetcher(tmp_path)
    with pytest.raises(SourceUnavailable):
        f.get("/missing.html", max_age=MAX_AGE_SEASON)


def test_token_bucket_allows_a_burst_then_throttles(monkeypatch, tmp_path):
    slept: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    f = Fetcher(Cache(tmp_path / "c.db"), Settings(min_interval=3.0, burst=3))
    for _ in range(3):
        f._throttle()  # burst — no sleeping
    assert slept == []
    f._throttle()  # bucket empty now
    assert slept and slept[-1] > 0


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("SWISH_PORT", "9999")
    monkeypatch.setenv("SWISH_OFFLINE", "1")
    monkeypatch.setenv("SWISH_MIN_INTERVAL", "1.5")
    s = settings_from_env()
    assert s.port == 9999
    assert s.offline is True
    assert s.min_interval == 1.5
