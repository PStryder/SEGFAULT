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
    base.py          - Persistence interface
    sqlite.py        - SQLite implementation
  tests/
    test_geometry.py - Segment intersection/diagonal legality
    test_collision.py- Process collision rules
    test_drift.py    - Drift constraints (connectivity, wall count)
    test_broadcast.py- Broadcast targeting + escalation reset
  web/
    index.html       - Home
    process.html     - Process UI
    spectate.html    - Spectator UI
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
