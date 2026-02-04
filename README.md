# SEGFAULT

SEGFAULT is a high-stress, tick-synchronous, terminal-only horror game where processes (humans and agents) navigate a shifting mainframe shard while a Defragmenter hunts instability. The authoritative design spec lives in `SEGFAULT.md`.

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

These choices are consistent with `SEGFAULT.md` but weren’t fully specified:
- **Gate drift** moves to **orthogonal** adjacent tiles (not diagonal).
- **Expanded visibility** renders tiles outside the local 3×3 with a blank digit (informational only). Movement still targets digits 1–9.
- **BUFFER movement** is resolved as a single tick with a randomized path; collisions are enforced on the final destination.
- **Spectator wall rendering** is a coarse marker in the 20×20 grid; edge‑accurate rendering is a UI enhancement for later.
- **Spectator inspection UI** (click-to-inspect) is not yet implemented in the minimal web UI.

If any assumption should change, update `SEGFAULT.md` and the engine implementation.

## Developer Commands

```bash
make dev      # run dev server
make test     # run pytest
make lint     # ruff
make format   # black
```
