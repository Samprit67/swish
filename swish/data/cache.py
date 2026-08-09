"""A tiny on-disk HTTP cache backed by SQLite.

Every page Swish fetches from Basketball-Reference lands here keyed by URL. The
model never touches this module; it exists so that the second time you ask about
a player the answer is instant and works with the network unplugged.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    url        TEXT PRIMARY KEY,
    body       TEXT NOT NULL,
    status     INTEGER NOT NULL,
    fetched_at REAL NOT NULL
);
"""


@dataclass(frozen=True)
class CachedPage:
    url: str
    body: str
    status: int
    fetched_at: float

    def age(self, now: float | None = None) -> float:
        return (now or time.time()) - self.fetched_at


class Cache:
    def __init__(self, path: Path | str):
        self.path = str(path)
        # the API serves sync endpoints from a threadpool over one connection
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def get(self, url: str) -> CachedPage | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT url, body, status, fetched_at FROM pages WHERE url = ?", (url,)
            ).fetchone()
        return CachedPage(*row) if row else None

    def put(self, url: str, body: str, status: int = 200) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO pages(url, body, status, fetched_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(url) DO UPDATE SET body=excluded.body, status=excluded.status, "
                "fetched_at=excluded.fetched_at",
                (url, body, status, time.time()),
            )
            self._conn.commit()

    def stats(self) -> dict[str, object]:
        with self._lock:
            n, total, oldest = self._conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(body)), 0), MIN(fetched_at) FROM pages"
            ).fetchone()
        return {"pages": n, "bytes": total, "oldest": oldest, "path": self.path}

    def clear(self) -> int:
        with self._lock:
            n = self._conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            self._conn.execute("DELETE FROM pages")
            self._conn.commit()
        return n

    def close(self) -> None:
        self._conn.close()
