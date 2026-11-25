"""Totales por espectador: sesión actual (memoria) e histórico (SQLite)."""

from __future__ import annotations

import sqlite3
import threading

from .bus import Event
from .config import DATA

METRICS = ("coins", "likes", "shares", "comments")
_EVENT_METRIC = {"gift": "coins", "like": "likes", "share": "shares", "chat": "comments"}


TEST_USER = "__prueba__"  # usuario de las pruebas de overlays

class Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(DATA / "streamops.db", check_same_thread=False)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS totals (
                   platform TEXT NOT NULL, user_id TEXT NOT NULL,
                   name TEXT, avatar TEXT,
                   coins REAL DEFAULT 0, likes REAL DEFAULT 0,
                   shares REAL DEFAULT 0, comments REAL DEFAULT 0,
                   PRIMARY KEY (platform, user_id))"""
        )
        self._db.commit()
        self._session: dict[tuple[str, str], dict] = {}
        self.counters = {"coins": 0.0, "likes": 0.0, "shares": 0.0, "follows": 0.0}
        self._test: dict[str, float] = {}
        self._test_follows = 0
        self.purge_tests()  # restos de pruebas de una ejecución anterior

    def record(self, event: Event) -> None:
        if event.type == "follow":
            self.counters["follows"] += 1
            if event.user_id.startswith(TEST_USER):
                self._test_follows += 1
        metric = _EVENT_METRIC.get(event.type)
        if not metric or not event.user_id:
            return
        if event.type == "gift":
            amount = float(event.value)
        elif event.type == "like":
            amount = float(event.count or 1)
        else:
            amount = 1.0
        if amount <= 0:
            return
        if metric in self.counters:
            self.counters[metric] += amount
        if event.user_id.startswith(TEST_USER):
            self._test[metric] = self._test.get(metric, 0.0) + amount
        key = (event.platform, event.user_id)
        with self._lock:
            row = self._session.setdefault(
                key, {"platform": event.platform, "name": event.user, "avatar": event.avatar, **{m: 0.0 for m in METRICS}}
            )
            row[metric] += amount
            row["name"] = event.user or row["name"]
            row["avatar"] = event.avatar or row["avatar"]
            self._db.execute(
                f"""INSERT INTO totals (platform, user_id, name, avatar, {metric}) VALUES (?,?,?,?,?)
                    ON CONFLICT(platform, user_id) DO UPDATE SET
                      {metric} = {metric} + excluded.{metric},
                      name = excluded.name,
                      avatar = CASE WHEN excluded.avatar != '' THEN excluded.avatar ELSE avatar END""",
                (event.platform, event.user_id, event.user, event.avatar, amount),
            )
            self._db.commit()

    def top(self, metric: str, scope: str = "session", limit: int = 10) -> list[dict]:
        if metric not in METRICS:
            return []
        limit = max(1, min(int(limit), 50))
        with self._lock:
            if scope == "all":
                rows = self._db.execute(
                    f"SELECT platform, name, avatar, {metric} FROM totals WHERE {metric} > 0 "
                    f"ORDER BY {metric} DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [{"platform": p, "name": n, "avatar": a, "value": v} for p, n, a, v in rows]
            rows = sorted(
                (r for r in self._session.values() if r[metric] > 0), key=lambda r: r[metric], reverse=True
            )[:limit]
            return [{"platform": r["platform"], "name": r["name"], "avatar": r["avatar"], "value": r[metric]} for r in rows]

    def snapshot(self, limit: int = 10) -> dict:
        return {
            "counters": dict(self.counters),
            "session": {m: self.top(m, "session", limit) for m in METRICS},
            "all": {m: self.top(m, "all", limit) for m in METRICS},
        }

    def purge_tests(self) -> bool:
        """Quita de tops y contadores lo que dejaron las pruebas de overlays."""
        with self._lock:
            found = bool(self._test) or self._test_follows > 0
            for metric, amount in self._test.items():
                if metric in self.counters:
                    self.counters[metric] = max(0.0, self.counters[metric] - amount)
            self.counters["follows"] = max(0.0, self.counters["follows"] - self._test_follows)
            self._test.clear()
            self._test_follows = 0
            for key in [k for k in self._session if k[1].startswith(TEST_USER)]:
                del self._session[key]
            self._db.execute("DELETE FROM totals WHERE user_id LIKE ?", (TEST_USER + "%",))
            self._db.commit()
        return found

    def reset_session(self) -> None:
        with self._lock:
            self._session.clear()
        for key in self.counters:
            self.counters[key] = 0.0

    def reset_all(self) -> None:
        self.reset_session()
        with self._lock:
            self._db.execute("DELETE FROM totals")
            self._db.commit()
