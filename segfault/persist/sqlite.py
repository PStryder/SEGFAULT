from __future__ import annotations

import random
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Tuple

from segfault.persist.base import Persistence


class SqlitePersistence(Persistence):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._pragmas = ("PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL")
        self._local = threading.local()
        self._init_db()

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
                CREATE TABLE IF NOT EXISTS leaderboard (
                    call_sign TEXT PRIMARY KEY,
                    survivals INTEGER NOT NULL DEFAULT 0,
                    deaths INTEGER NOT NULL DEFAULT 0,
                    ghosts INTEGER NOT NULL DEFAULT 0
                )
                """)
        conn.execute("""
                CREATE TABLE IF NOT EXISTS flavor_text (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel TEXT NOT NULL,
                    text TEXT NOT NULL UNIQUE,
                    created_at INTEGER NOT NULL
                )
                """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_flavor_channel_id ON flavor_text(channel, id)")
        conn.commit()

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        for pragma in self._pragmas:
            conn.execute(pragma)

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            self._apply_pragmas(conn)
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def _ensure_row(self, conn: sqlite3.Connection, call_sign: str) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO leaderboard(call_sign, survivals, deaths, ghosts) VALUES (?,0,0,0)",
            (call_sign,),
        )

    def record_survival(self, call_sign: str) -> None:
        conn = self._get_conn()
        self._ensure_row(conn, call_sign)
        conn.execute(
            "UPDATE leaderboard SET survivals = survivals + 1 WHERE call_sign = ?",
            (call_sign,),
        )
        conn.commit()

    def record_death(self, call_sign: str) -> None:
        conn = self._get_conn()
        self._ensure_row(conn, call_sign)
        conn.execute(
            "UPDATE leaderboard SET deaths = deaths + 1 WHERE call_sign = ?",
            (call_sign,),
        )
        conn.commit()

    def record_ghost(self, call_sign: str) -> None:
        conn = self._get_conn()
        self._ensure_row(conn, call_sign)
        conn.execute(
            "UPDATE leaderboard SET ghosts = ghosts + 1 WHERE call_sign = ?",
            (call_sign,),
        )
        conn.commit()

    def leaderboard(self) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT call_sign, survivals, deaths, ghosts FROM leaderboard ORDER BY survivals DESC, deaths ASC"
        ).fetchall()
        return [
            {
                "call_sign": r[0],
                "survivals": r[1],
                "deaths": r[2],
                "ghosts": r[3],
            }
            for r in rows
        ]

    def flavor_count(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM flavor_text").fetchone()
        return int(row[0]) if row else 0

    def seed_flavor_from_markdown(self, md_path: str) -> int:
        entries = self._parse_flavor_markdown(md_path)
        if not entries:
            return 0
        now = int(time.time())
        rows = [(channel, text, now) for channel, text in entries]
        conn = self._get_conn()
        before = conn.execute("SELECT COUNT(*) FROM flavor_text").fetchone()
        before_count = int(before[0]) if before else 0
        conn.executemany(
            "INSERT OR IGNORE INTO flavor_text(channel, text, created_at) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM flavor_text").fetchone()
        after_count = int(after[0]) if after else before_count
        return max(0, after_count - before_count)

    def random_flavor(self, channel: str | None = None) -> Dict[str, str] | None:
        conn = self._get_conn()
        row = self._random_flavor_row(conn, channel)
        if not row:
            return None
        return {"text": row[0], "channel": row[1]}

    def _random_flavor_row(
        self, conn: sqlite3.Connection, channel: str | None
    ) -> Tuple[str, str] | None:
        if channel:
            min_max = conn.execute(
                "SELECT MIN(id), MAX(id) FROM flavor_text WHERE channel = ?",
                (channel,),
            ).fetchone()
        else:
            min_max = conn.execute("SELECT MIN(id), MAX(id) FROM flavor_text").fetchone()
        if not min_max or min_max[0] is None:
            return None
        min_id, max_id = int(min_max[0]), int(min_max[1])
        target = random.randint(min_id, max_id)
        if channel:
            row = conn.execute(
                "SELECT text, channel FROM flavor_text WHERE channel = ? AND id >= ? ORDER BY id LIMIT 1",
                (channel, target),
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT text, channel FROM flavor_text WHERE channel = ? AND id < ? ORDER BY id LIMIT 1",
                    (channel, target),
                ).fetchone()
        else:
            row = conn.execute(
                "SELECT text, channel FROM flavor_text WHERE id >= ? ORDER BY id LIMIT 1",
                (target,),
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT text, channel FROM flavor_text WHERE id < ? ORDER BY id LIMIT 1",
                    (target,),
                ).fetchone()
        return row

    def _parse_flavor_markdown(self, md_path: str) -> List[Tuple[str, str]]:
        path = Path(md_path)
        if not path.exists():
            return []
        lines: List[Tuple[str, str]] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if not line.startswith("-"):
                continue
            line = line.lstrip("-").strip()
            if not line:
                continue
            channel = "sys"
            if line.startswith("[") and "]" in line:
                tag = line[1 : line.index("]")].strip().upper()
                rest = line[line.index("]") + 1 :].strip()
                if tag in {"PROC", "SPEC", "SYS"}:
                    channel = tag.lower()
                    line = rest
            if not line:
                continue
            lines.append((channel, line))
        return lines
