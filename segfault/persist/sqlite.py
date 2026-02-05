from __future__ import annotations

import base64
import json
import logging
import queue
import random
import sqlite3
import threading
import time
import zlib
from collections.abc import Callable
from pathlib import Path

from segfault.persist.base import Persistence

logger = logging.getLogger(__name__)


class SqlitePersistence(Persistence):
    def __init__(
        self,
        db_path: str,
        replay_compress: bool = False,
        replay_max_ticks: int = 0,
        replay_max_shards: int = 0,
    ) -> None:
        self.db_path = db_path
        self._pragmas = (
            "PRAGMA journal_mode=WAL",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA busy_timeout=5000",
        )
        self._local = threading.local()
        self._replay_compress = replay_compress
        self._replay_max_ticks = replay_max_ticks
        self._replay_max_shards = replay_max_shards
        self._init_db()
        self._write_queue: queue.Queue[
            tuple[Callable[[sqlite3.Connection], object], threading.Event, dict[str, object]] | None
        ] = queue.Queue()
        self._writer_stop = threading.Event()
        self._writer_thread = threading.Thread(
            target=self._writer_loop, name="sqlite-writer", daemon=True
        )
        self._writer_thread.start()

    def _writer_loop(self) -> None:
        conn = sqlite3.connect(self.db_path)
        self._apply_pragmas(conn)
        while True:
            task = self._write_queue.get()
            if task is None:
                self._write_queue.task_done()
                break
            fn, event, holder = task
            try:
                holder["result"] = fn(conn)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                holder["error"] = exc
                logger.exception("SQLite write failed")
            finally:
                event.set()
                self._write_queue.task_done()
        conn.close()

    def _run_write(self, fn: Callable[[sqlite3.Connection], object], wait: bool = True):
        if self._writer_stop.is_set():
            raise RuntimeError("Persistence writer stopped")
        event = threading.Event()
        holder: dict[str, object] = {"result": None, "error": None}
        self._write_queue.put((fn, event, holder))
        if not wait:
            return None
        event.wait()
        if holder["error"] is not None:
            raise holder["error"]
        return holder["result"]

    def flush(self) -> None:
        self._write_queue.join()

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
        conn.execute("""
                CREATE TABLE IF NOT EXISTS replay_ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    shard_id TEXT NOT NULL,
                    tick INTEGER NOT NULL,
                    snapshot TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    UNIQUE(shard_id, tick)
                )
                """)
        conn.execute("""
                CREATE TABLE IF NOT EXISTS replay_shards (
                    shard_id TEXT PRIMARY KEY,
                    started_at INTEGER NOT NULL,
                    ended_at INTEGER,
                    total_ticks INTEGER DEFAULT 0,
                    total_processes INTEGER DEFAULT 0,
                    total_kills INTEGER DEFAULT 0,
                    total_survivals INTEGER DEFAULT 0,
                    total_ghosts INTEGER DEFAULT 0
                )
                """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_flavor_channel_id ON flavor_text(channel, id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_replay_shard_tick ON replay_ticks(shard_id, tick)"
        )
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
        self.flush()
        self._writer_stop.set()
        self._write_queue.put(None)
        self._writer_thread.join(timeout=2)
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
        def _task(conn: sqlite3.Connection) -> None:
            self._ensure_row(conn, call_sign)
            conn.execute(
                "UPDATE leaderboard SET survivals = survivals + 1 WHERE call_sign = ?",
                (call_sign,),
            )

        self._run_write(_task, wait=False)

    def record_death(self, call_sign: str) -> None:
        def _task(conn: sqlite3.Connection) -> None:
            self._ensure_row(conn, call_sign)
            conn.execute(
                "UPDATE leaderboard SET deaths = deaths + 1 WHERE call_sign = ?",
                (call_sign,),
            )

        self._run_write(_task, wait=False)

    def record_ghost(self, call_sign: str) -> None:
        def _task(conn: sqlite3.Connection) -> None:
            self._ensure_row(conn, call_sign)
            conn.execute(
                "UPDATE leaderboard SET ghosts = ghosts + 1 WHERE call_sign = ?",
                (call_sign,),
            )

        self._run_write(_task, wait=False)

    def leaderboard(self) -> list[dict]:
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

        def _task(conn: sqlite3.Connection) -> int:
            before = conn.execute("SELECT COUNT(*) FROM flavor_text").fetchone()
            before_count = int(before[0]) if before else 0
            conn.executemany(
                "INSERT OR IGNORE INTO flavor_text(channel, text, created_at) VALUES (?, ?, ?)",
                rows,
            )
            after = conn.execute("SELECT COUNT(*) FROM flavor_text").fetchone()
            after_count = int(after[0]) if after else before_count
            return max(0, after_count - before_count)

        inserted = self._run_write(_task, wait=True)
        return int(inserted) if inserted is not None else 0

    def random_flavor(self, channel: str | None = None) -> dict[str, str] | None:
        conn = self._get_conn()
        row = self._random_flavor_row(conn, channel)
        if not row:
            return None
        return {"text": row[0], "channel": row[1]}

    def _random_flavor_row(
        self, conn: sqlite3.Connection, channel: str | None
    ) -> tuple[str, str] | None:
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

    def _parse_flavor_markdown(self, md_path: str) -> list[tuple[str, str]]:
        path = Path(md_path)
        if not path.exists():
            return []
        lines: list[tuple[str, str]] = []
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

    def record_replay_tick(self, shard_id: str, tick: int, snapshot: dict) -> None:
        payload = self._encode_snapshot(snapshot)
        created_at = int(time.time())

        def _task(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT OR IGNORE INTO replay_ticks(shard_id, tick, snapshot, created_at) "
                "VALUES (?, ?, ?, ?)",
                (shard_id, tick, payload, created_at),
            )
            if self._replay_max_ticks > 0:
                cutoff = tick - self._replay_max_ticks
                if cutoff >= 0:
                    conn.execute(
                        "DELETE FROM replay_ticks WHERE shard_id = ? AND tick <= ?",
                        (shard_id, cutoff),
                    )

        self._run_write(_task, wait=False)

    def register_replay_shard(self, shard_id: str) -> None:
        started_at = int(time.time())

        def _task(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT OR IGNORE INTO replay_shards(shard_id, started_at) VALUES (?, ?)",
                (shard_id, started_at),
            )
            self._enforce_replay_shard_limit(conn)

        self._run_write(_task, wait=False)

    def finalize_replay_shard(self, shard_id: str, total_ticks: int, stats: dict) -> None:
        ended_at = int(time.time())
        total_processes = int(stats.get("total_processes", 0))
        total_kills = int(stats.get("total_kills", 0))
        total_survivals = int(stats.get("total_survivals", 0))
        total_ghosts = int(stats.get("total_ghosts", 0))

        def _task(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE replay_shards SET ended_at = ?, total_ticks = ?, total_processes = ?, "
                "total_kills = ?, total_survivals = ?, total_ghosts = ? WHERE shard_id = ?",
                (
                    ended_at,
                    total_ticks,
                    total_processes,
                    total_kills,
                    total_survivals,
                    total_ghosts,
                    shard_id,
                ),
            )
            self._enforce_replay_shard_limit(conn)

        self._run_write(_task, wait=False)

    def list_replay_shards(self, limit: int = 50) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT shard_id, started_at, ended_at, total_ticks, total_processes, "
            "total_kills, total_survivals, total_ghosts "
            "FROM replay_shards ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "shard_id": row[0],
                "started_at": row[1],
                "ended_at": row[2],
                "total_ticks": row[3],
                "total_processes": row[4],
                "total_kills": row[5],
                "total_survivals": row[6],
                "total_ghosts": row[7],
            }
            for row in rows
        ]

    def get_replay_ticks(self, shard_id: str, start_tick: int = 0, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT tick, snapshot FROM replay_ticks WHERE shard_id = ? AND tick >= ? "
            "ORDER BY tick ASC LIMIT ?",
            (shard_id, start_tick, limit),
        ).fetchall()
        result: list[dict] = []
        for tick, snapshot in rows:
            result.append({"tick": tick, "snapshot": self._decode_snapshot(snapshot)})
        return result

    def _encode_snapshot(self, snapshot: dict) -> str:
        payload = json.dumps(snapshot, separators=(",", ":"))
        if not self._replay_compress:
            return payload
        compressed = zlib.compress(payload.encode("utf-8"))
        encoded = base64.b64encode(compressed).decode("ascii")
        return f"zlib:{encoded}"

    def _decode_snapshot(self, payload: str) -> dict:
        if payload.startswith("zlib:"):
            encoded = payload.split(":", 1)[1]
            raw = zlib.decompress(base64.b64decode(encoded)).decode("utf-8")
            return json.loads(raw)
        return json.loads(payload)

    def _enforce_replay_shard_limit(self, conn: sqlite3.Connection) -> None:
        if self._replay_max_shards <= 0:
            return
        active_rows = conn.execute(
            "SELECT shard_id FROM replay_shards WHERE ended_at IS NULL"
        ).fetchall()
        active_ids = [row[0] for row in active_rows]
        remaining = max(0, self._replay_max_shards - len(active_ids))
        keep_ids = list(active_ids)
        if remaining > 0:
            rows = conn.execute(
                "SELECT shard_id FROM replay_shards WHERE ended_at IS NOT NULL "
                "ORDER BY started_at DESC LIMIT ?",
                (remaining,),
            ).fetchall()
            keep_ids.extend(row[0] for row in rows)
        if not keep_ids:
            return
        placeholders = ",".join("?" for _ in keep_ids)
        conn.execute(
            f"DELETE FROM replay_ticks WHERE shard_id NOT IN ({placeholders})",
            keep_ids,
        )
        conn.execute(
            f"DELETE FROM replay_shards WHERE shard_id NOT IN ({placeholders})",
            keep_ids,
        )
