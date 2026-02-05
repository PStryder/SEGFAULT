# Codex Task: Replay Logger + Replay Viewer

## Context

SEGFAULT is a tick-synchronous horror game. The tick engine (`segfault/engine/engine.py`) advances all shards each tick. Every tick produces a complete, deterministic state snapshot. We need to capture these snapshots as replay logs and build a web UI to play them back.

**Why:** Replay data is the training corpus for future custom Defragmenter AI personalities. It's also a spectator feature — watch past games, study strategies, share notable runs.

Read `SEGFAULT.md` for the full game spec. Read `REPO_MAP.md` for file layout. Read all existing code before writing anything.

---

## Part 1: Replay Logger

### 1.1 Schema

Add a new table to the SQLite persistence layer. In `segfault/persist/sqlite.py`, add to `_init_db`:

```sql
CREATE TABLE IF NOT EXISTS replay_ticks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shard_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    snapshot TEXT NOT NULL,       -- JSON blob of full tick state
    created_at INTEGER NOT NULL,  -- unix epoch seconds
    UNIQUE(shard_id, tick)
);
CREATE INDEX IF NOT EXISTS idx_replay_shard_tick ON replay_ticks(shard_id, tick);
```

Add a second table for shard-level replay metadata:

```sql
CREATE TABLE IF NOT EXISTS replay_shards (
    shard_id TEXT PRIMARY KEY,
    started_at INTEGER NOT NULL,
    ended_at INTEGER,                -- NULL while shard is live
    total_ticks INTEGER DEFAULT 0,
    total_processes INTEGER DEFAULT 0,
    total_kills INTEGER DEFAULT 0,
    total_survivals INTEGER DEFAULT 0,
    total_ghosts INTEGER DEFAULT 0
);
```

### 1.2 Snapshot Format

Each `snapshot` JSON blob must contain EVERYTHING needed to reconstruct the tick visually and for ML training. Serialize the following per tick:

```json
{
  "shard_id": "...",
  "tick": 42,
  "grid_size": 20,
  "walls": [[ax, ay, bx, by], ...],
  "gates": [{"pos": [x, y], "type": "stable|ghost"}, ...],
  "processes": [
    {
      "id": "...",
      "call_sign": "...",
      "pos": [x, y],
      "alive": true,
      "buffered_cmd": "MOVE",
      "buffered_arg": "6",
      "los_lock": false,
      "last_sprint_tick": -999
    }
  ],
  "defragger": {
    "pos": [x, y],
    "target_id": "..." or null,
    "target_reason": "broadcast|los|patrol|watchdog"
  },
  "watchdog": {
    "quiet_ticks": 0,
    "countdown": 0,
    "active": false,
    "bonus_step": 0
  },
  "broadcasts": [{"process_id": "...", "message": "...", "timestamp_ms": 0}],
  "say_events": [
    {
      "sender_id": "...",
      "sender_pos": [x, y],
      "message": "...",
      "recipients": [{"id": "...", "pos": [x, y]}]
    }
  ],
  "echo_tiles": [{"pos": [x, y], "tick": 40}],
  "events": {
    "kills": ["process_id", ...],
    "survivals": ["process_id", ...],
    "ghosts": ["process_id", ...],
    "spawns": ["process_id", ...]
  }
}
```

### 1.3 Persistence Methods

Add to `segfault/persist/base.py` abstract interface:

```python
@abstractmethod
def record_replay_tick(self, shard_id: str, tick: int, snapshot: dict) -> None:
    raise NotImplementedError

@abstractmethod
def register_replay_shard(self, shard_id: str) -> None:
    raise NotImplementedError

@abstractmethod
def finalize_replay_shard(self, shard_id: str, total_ticks: int, stats: dict) -> None:
    raise NotImplementedError

@abstractmethod
def list_replay_shards(self, limit: int = 50) -> list[dict]:
    raise NotImplementedError

@abstractmethod
def get_replay_ticks(self, shard_id: str, start_tick: int = 0, limit: int = 100) -> list[dict]:
    raise NotImplementedError
```

Implement all in `segfault/persist/sqlite.py`. Use the existing `_run_write` pattern for writes (fire-and-forget, `wait=False`). Reads use `_get_conn()` directly (same pattern as `leaderboard()`).

`record_replay_tick` must serialize the snapshot dict to JSON via `json.dumps`. `get_replay_ticks` must deserialize back via `json.loads`.

### 1.4 Engine Integration

In `segfault/engine/engine.py`:

**In `_tick_shard`**, after all tick resolution is complete (after broadcasts clear, after watchdog advancement, after echo trimming), call a new method `_record_tick_snapshot(shard)` that:

1. Builds the snapshot dict from current shard state (use the format above)
2. Calls `self.persistence.record_replay_tick(shard.shard_id, shard.tick, snapshot)`

**Track tick events** — the snapshot needs to know which processes were killed/survived/ghosted/spawned THIS tick. Add a transient field to `ShardState`:

```python
@dataclass
class TickEvents:
    kills: list[str] = field(default_factory=list)
    survivals: list[str] = field(default_factory=list)
    ghosts: list[str] = field(default_factory=list)
    spawns: list[str] = field(default_factory=list)
```

Add `tick_events: TickEvents = field(default_factory=TickEvents)` to `ShardState`. Reset it at the START of `_tick_shard`. Populate it in `_kill_process`, `_resolve_gate_interactions` (stable = survival, ghost = ghost), and `join_process`. Include it in the snapshot.

**In `create_shard`**, call `self.persistence.register_replay_shard(shard.shard_id)`.

**In the shard shutdown block** (where `self.shards.pop` happens), call:
```python
self.persistence.finalize_replay_shard(
    shard.shard_id,
    total_ticks=shard.tick,
    stats={
        "total_processes": ...,  # count from replay_ticks or track on ShardState
        "total_kills": ...,
        "total_survivals": ...,
        "total_ghosts": ...,
    }
)
```

Track cumulative kill/survival/ghost counts on `ShardState` by incrementing counters in the appropriate methods.

### 1.5 Configuration

Add to `segfault/common/config.py` Settings:

```python
enable_replay_logging: bool = _env_bool(os.getenv("SEGFAULT_REPLAY_LOGGING", "1"))
```

Gate the `_record_tick_snapshot` call behind this flag. Default ON.

### 1.6 Defragger target_reason tracking

Currently `DefragmenterState.target_reason` exists but is never set. Fix this:
- In `_select_defragger_target`, set `shard.defragger.target_reason` to `"broadcast"`, `"los"`, `"watchdog"`, or `"patrol"` (when no target) as appropriate before returning.
- Include it in the replay snapshot.

---

## Part 2: Replay API Endpoints

Add to `segfault/api/app.py`:

### `GET /replays`

List available replay shards. Returns:
```json
{
  "shards": [
    {
      "shard_id": "...",
      "started_at": 1234567890,
      "ended_at": 1234568000,
      "total_ticks": 120,
      "total_processes": 8,
      "total_kills": 5,
      "total_survivals": 2,
      "total_ghosts": 1
    }
  ]
}
```
Optional query param `?limit=50`. Default 50. Ordered by `started_at DESC` (newest first).

### `GET /replays/{shard_id}`

Get replay tick data for a shard. Query params:
- `start_tick` (default 0)
- `limit` (default 100, max 500)

Returns:
```json
{
  "shard_id": "...",
  "ticks": [
    { "tick": 0, "snapshot": { ... } },
    { "tick": 1, "snapshot": { ... } }
  ],
  "has_more": true
}
```

Both endpoints require API key if configured (same `_check_api_key` pattern).

### Pydantic Models

Add to `segfault/api/models.py`:
- `ReplayShardSummary` — fields matching the list response
- `ReplayTickEntry` — tick int + snapshot dict
- `ReplayResponse` — shard_id, ticks list, has_more bool

---

## Part 3: Replay Viewer Web UI

Create `segfault/web/replay.html` and add route:

```python
@app.get("/replay")
def replay_ui() -> FileResponse:
    return FileResponse("segfault/web/replay.html")
```

### Viewer Requirements

**Layout:** Match existing spectator aesthetic. Use `style.css`. Terminal dark theme. Monospace everything.

**Shard selector panel:**
- Fetch `/replays` on load
- Show shard list with: shard_id (truncated), total ticks, process count, kill count, time range
- Click to load replay

**Playback controls:**
- Play / Pause button
- Step forward / Step backward (single tick)
- Speed control: 0.5x, 1x, 2x, 4x (relative to original tick_seconds=10)
- Tick slider / scrubber showing current position in total ticks
- Current tick number display

**Grid rendering:**
- Reuse the spectator grid rendering approach (CSS grid, colored cells)
- Show: processes (green), defragger (red), gates (blue), echo tiles (grey/italic), walls (#)
- Show defragger target with connecting indicator (highlight target process)
- Show defragger `target_reason` as text label

**Side panels:**
- **Watchdog panel:** quiet_ticks, countdown, active, bonus_step (same as spectator)
- **Events panel:** Show kills, survivals, ghosts, spawns for current tick
- **Broadcasts panel:** Show any broadcasts this tick
- **Say traces panel:** Show say events with sender/recipient positions
- **Process list:** All processes with position, alive status, call_sign

**Data loading:**
- Fetch ticks in chunks of 100 via `/replays/{shard_id}?start_tick=N&limit=100`
- Pre-fetch next chunk when playback reaches 80% of current buffer
- Cache fetched chunks in memory (don't re-fetch)

**Playback engine (JavaScript):**
```javascript
class ReplayPlayer {
    constructor() {
        this.ticks = [];        // loaded tick snapshots
        this.currentIndex = 0;
        this.playing = false;
        this.speed = 1.0;
        this.intervalId = null;
    }
    
    play() { ... }
    pause() { ... }
    stepForward() { ... }
    stepBackward() { ... }
    seekTo(tick) { ... }
    setSpeed(multiplier) { ... }
}
```

The playback interval should be `(tick_seconds * 1000) / speed` milliseconds. Default tick_seconds = 10, so 1x = 10s per tick, 4x = 2.5s per tick.

**URL state:**
- Support `?shard=SHARD_ID&tick=N` query params so replays are linkable
- Update URL on shard selection and during playback (use `replaceState`, don't spam history)

### Navigation

Add "Replay" link to:
- `index.html` nav section
- `spectator.html` nav section

---

## Part 4: Tests

Create `segfault/tests/test_replay.py`:

### test_replay_tick_recorded
- Create engine with DummyPersist replaced by a real SqlitePersistence (tmpdir)
- Create shard, join two processes, tick once
- Verify `replay_ticks` table has one row for tick 1
- Verify snapshot JSON contains expected keys: shard_id, tick, walls, gates, processes, defragger, watchdog

### test_replay_tick_events_tracked
- Create engine, join process, place on gate position manually, tick (triggers survival/ghost)
- Verify tick_events in snapshot contains the correct event type

### test_replay_shard_lifecycle
- Create shard → verify `replay_shards` row exists with `ended_at=NULL`
- Run enough empty ticks to trigger shard shutdown
- Verify `ended_at` is populated and `total_ticks` matches

### test_replay_disabled_by_config
- Monkeypatch `settings.enable_replay_logging = False`
- Create engine, tick, verify no rows in `replay_ticks`

### test_replay_tick_snapshot_format
- Create engine with known seed, create shard, join process
- Tick once, retrieve snapshot
- Validate every field in the snapshot format spec (walls are list of 4-int lists, processes have all required fields, etc.)

---

## Part 5: Update REPO_MAP.md

Add the new files to the repo map. Update the `persist/` section to mention replay tables.

---

## Constraints

- Follow existing code style exactly (black, ruff, 100-char lines)
- Use existing patterns: `_run_write` for async writes, `_get_conn()` for reads
- No new dependencies — everything uses stdlib json, sqlite3, existing FastAPI
- All new code must have type hints
- Replay logging must not slow down the tick loop — writes are fire-and-forget
- The replay viewer must work with the existing `style.css` — extend it, don't replace it
- Test with `pytest` — all existing tests must still pass
- Run `make lint` and `make fmt` before committing

## File Checklist

Files to MODIFY:
- `segfault/persist/base.py` — add abstract methods
- `segfault/persist/sqlite.py` — add replay tables, implement methods
- `segfault/engine/state.py` — add TickEvents dataclass, add to ShardState, add counters
- `segfault/engine/engine.py` — add snapshot recording, populate tick_events, track target_reason
- `segfault/common/config.py` — add enable_replay_logging
- `segfault/api/app.py` — add replay endpoints and replay route
- `segfault/api/models.py` — add replay Pydantic models
- `segfault/web/index.html` — add Replay nav link
- `segfault/web/spectator.html` — add Replay nav link
- `REPO_MAP.md` — update

Files to CREATE:
- `segfault/web/replay.html` — replay viewer UI
- `segfault/tests/test_replay.py` — replay tests
