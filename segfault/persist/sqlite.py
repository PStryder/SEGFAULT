from __future__ import annotations

import sqlite3
from typing import Dict, List

from segfault.persist.base import Persistence


class SqlitePersistence(Persistence):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._pragmas = ("PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL")
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            self._apply_pragmas(conn)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leaderboard (
                    call_sign TEXT PRIMARY KEY,
                    survivals INTEGER NOT NULL DEFAULT 0,
                    deaths INTEGER NOT NULL DEFAULT 0,
                    ghosts INTEGER NOT NULL DEFAULT 0
                )
                """)
            conn.commit()

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        for pragma in self._pragmas:
            conn.execute(pragma)

    def _ensure_row(self, conn: sqlite3.Connection, call_sign: str) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO leaderboard(call_sign, survivals, deaths, ghosts) VALUES (?,0,0,0)",
            (call_sign,),
        )

    def record_survival(self, call_sign: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            self._apply_pragmas(conn)
            self._ensure_row(conn, call_sign)
            conn.execute(
                "UPDATE leaderboard SET survivals = survivals + 1 WHERE call_sign = ?",
                (call_sign,),
            )
            conn.commit()

    def record_death(self, call_sign: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            self._apply_pragmas(conn)
            self._ensure_row(conn, call_sign)
            conn.execute(
                "UPDATE leaderboard SET deaths = deaths + 1 WHERE call_sign = ?",
                (call_sign,),
            )
            conn.commit()

    def record_ghost(self, call_sign: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            self._apply_pragmas(conn)
            self._ensure_row(conn, call_sign)
            conn.execute(
                "UPDATE leaderboard SET ghosts = ghosts + 1 WHERE call_sign = ?",
                (call_sign,),
            )
            conn.commit()

    def leaderboard(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            self._apply_pragmas(conn)
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
