"""Runtime configuration and where Swish keeps its cache.

Swish holds no permanent data of its own. Everything it fetches from
Basketball-Reference goes into a single SQLite cache file under the platform's
data directory (or ``$SWISH_HOME`` if set). Delete that file and Swish forgets
everything it has ever downloaded.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "swish"

# Basketball-Reference asks crawlers to stay under 20 requests/minute and will
# hand out a one-hour block for ignoring it. A sustained 3s gap (with a small
# burst allowance) keeps us comfortably inside that with margin for retries.
DEFAULT_MIN_INTERVAL = 3.0


def data_home() -> Path:
    if env := os.environ.get("SWISH_HOME"):
        return Path(env).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def default_cache_path() -> Path:
    return data_home() / "cache.db"


@dataclass
class Settings:
    cache_path: Path = field(default_factory=default_cache_path)
    host: str = "127.0.0.1"
    port: int = 8770
    #: sustained seconds between outbound requests to Basketball-Reference
    min_interval: float = DEFAULT_MIN_INTERVAL
    #: how many requests may fire back-to-back before the sustained rate kicks in
    burst: int = 4
    #: allow the network at all; when False only the cache is consulted
    offline: bool = False
    user_agent: str = "swish/0.3 (personal trade-value tool; +https://github.com/sgoswami/swish)"

    @property
    def cache_url(self) -> str:
        if str(self.cache_path) == ":memory:":
            return ":memory:"
        return str(self.cache_path)

    def ensure_dirs(self) -> None:
        if str(self.cache_path) != ":memory:":
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)


def settings_from_env() -> Settings:
    s = Settings()
    if path := os.environ.get("SWISH_CACHE"):
        s.cache_path = Path(path).expanduser()
    if host := os.environ.get("SWISH_HOST"):
        s.host = host
    if port := os.environ.get("SWISH_PORT"):
        s.port = int(port)
    if interval := os.environ.get("SWISH_MIN_INTERVAL"):
        s.min_interval = float(interval)
    if burst := os.environ.get("SWISH_BURST"):
        s.burst = int(burst)
    if os.environ.get("SWISH_OFFLINE"):
        s.offline = True
    return s
