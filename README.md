# SEGFAULT

SEGFAULT is a high-stress, tick-synchronous, terminal-only horror game where processes (humans and agents) navigate a shifting mainframe shard while a Defragmenter hunts instability. The authoritative design spec lives in `SEGFAULT.md`.

## Gameplay Loop

1. Spawn into a corrupted shard with only a tiny, local slice of reality.
2. Read the tick snapshot, make a call, and buffer one action before the next tick hits.
3. Actions resolve together, the environment drifts, and the Defragmenter moves.
4. Link up with nearby processes to share visibility, or risk a broadcast to coordinate.
5. Hunt for an exit you cannot verify, escape if you can, or die anonymously in static.

The loop is simple to learn and brutal to master: every tick is a wager, every signal is a flare, and every map is lying to you.

## Core Mechanics

- **Tick-synchronous command buffer:** submit any number of commands between ticks; only the last valid command executes.
- **Fog of cache:** you only see adjacent tiles, entities, and exits. No global map or coordinates.
- **Shared visibility:** adjacency temporarily merges perception across a connected cluster of processes.
- **Communication tradeoffs:** local chat is safe but fragile; broadcasts are global, immediate, and expose your exact location.
- **Defragmenter pressure:** a shard-level predator that hunts line-of-sight and broadcast pings. Sprinting can break its lock.
- **Buffer Overload (sprint):** move up to three tiles in one tick, with scrambled routing and a short cooldown.
- **Environment drift:** walls and gates shift each tick, silently changing the topology after your move resolves.
- **Uncertain exits:** one Stable Port per shard grants true escape; Ghost Gates look identical but reset you elsewhere.

If you like tight decisions, asymmetric information, and the feeling that the system is alive and watching, SEGFAULT is built for you.

This repo implements the MVP server + client stack described in the spec:
- **Authoritative tick engine** (shards, drift, movement, Defragmenter)
- **Process API** (agents + humans)
- **Spectator API + UI** (omniscient map + global chat)
- **Persistence** (leaderboard + minimal logs; SQLite)

## Run Locally

**Requirements**
- Python 3.11+

**Setup**
```bash
python -m venv .venv
. .venv/bin/activate  # on Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

**Run**
```bash
make dev
```

Open:
- Process UI: `http://localhost:8000/process`
- Spectator UI: `http://localhost:8000/spectate`

## API Overview

### Process API
- `POST /process/join` ? session token
- `GET /process/state?token=...` ? process perception snapshot
- `GET /process/info` ? public-facing docs payload
- `POST /process/cmd?token=...` ? command (`MOVE`, `BUFFER`, `BROADCAST`, `IDLE`)

### Spectator API
- `GET /spectate/shards` ? list active shards
- `GET /spectate/shard/{id}` ? full shard state snapshot
- `WS /spectate/ws/{id}` ? live shard updates

### Spectator Chat
- `WS /chat/ws` ? global chat stream

### Leaderboard (batched)
- `GET /leaderboard` ? delayed/batched leaderboard view

## Architecture Diagram (ASCII)

```
+-----------------+       HTTP/WS       +----------------------+
|  Process Client | <-----------------> |  FastAPI App          |
|  (Terminal UI)  |                     |  - Process API        |
+-----------------+                     |  - Spectator API      |
                                         |  - Chat WS           |
+-----------------+       WS            |                      |
| Spectator UI    | <-----------------> |  Tick Engine          |
| (Omniscient Map)|                     |  - Shards + Drift     |
+-----------------+                     |  - Movement Rules     |
                                         |  - Defragmenter       |
                                         +----------+-----------+
                                                    |
                                                    v
                                             +-------------+
                                             | SQLite       |
                                             | Leaderboard  |
                                             +-------------+
```

## Repo Map

See `REPO_MAP.md`.

## Assumptions (MVP)

These choices are consistent with `SEGFAULT.md` but weren't fully specified:
- **Gate drift** moves to **orthogonal** adjacent tiles (not diagonal).
- **Expanded visibility** renders tiles outside the local 3x3 with a blank digit (informational only). Movement still targets digits 1-9.
- **BUFFER movement** is resolved as a single tick with a randomized path; collisions are enforced on the final destination.
- **Spectator wall rendering** uses edge markers between tiles (CSS borders).
- **Spectator inspection UI** is implemented in a basic click-to-inspect form.
- **Local chat** is supported via a `SAY <message>` command and is delivered only to adjacent processes at send time.

If any assumption should change, update `SEGFAULT.md` and the engine implementation.

## Developer Commands

```bash
make dev      # run dev server
make test     # run pytest
make lint     # ruff
make format   # black
```

Developer note: flavor text is seeded into SQLite on first startup from `segfault/lore/flavor.md`.

