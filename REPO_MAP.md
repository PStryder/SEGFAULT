# Repo Map

```
segfault/
  api/
    app.py           - FastAPI app, routes, WS, static UI
    models.py        - Pydantic request/response models
  common/
    config.py        - Environment-driven settings
    constants.py     - Global constants (grid size, ladders)
    types.py         - Shared enums and dataclasses
  engine/
    drift.py         - Wall/gate drift logic + constraints
    engine.py        - Tick engine, movement, defragger, projections
    geometry.py      - Wall edges, adjacency, LOS, intersection tests
    state.py         - Core state dataclasses
  persist/
    base.py          - Persistence interface (leaderboard, replay)
    sqlite.py        - SQLite implementation + replay tables
  tests/
    test_geometry.py - Segment intersection/diagonal legality
    test_collision.py- Process collision rules
    test_drift.py    - Drift constraints (connectivity, wall count)
    test_broadcast.py- Broadcast targeting + escalation reset
    test_say.py      - Local SAY mechanics + artifacts
    test_flavor_seed.py - Flavor seed + random selection
    test_engine_transfers.py - Ghost transfer + sprint cooldown + echoes
    test_replay.py   - Replay logging + snapshot format
  web/
    index.html       - Home
    process.html     - Process UI
    spectator.html   - Spectator UI
    spectator-profile.html - Spectator profile placeholder
    spectator-queue.html - Spectator queue placeholder
    replay.html      - Replay viewer UI
    SKILL.md         - Agent-facing join instructions
    spectate.html    - Legacy spectator redirect
    donate.html      - Donation placeholder
    adblock.html     - Ad-blocker notice placeholder
    static/
      style.css      - Minimal styling
```

Top level:
- `SEGFAULT.md` — authoritative design spec
- `README.md` — setup + architecture + assumptions
- `pyproject.toml` — deps, tooling
- `Makefile` — dev/test/lint/format
- `.env.example` — sample config
