from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables.

    Keep this minimal and explicit for MVP. This can be swapped for
    Pydantic Settings later if needed.
    """

    db_path: str = os.getenv("SEGFAULT_DB_PATH", "segfault.db")
    tick_seconds: int = int(os.getenv("SEGFAULT_TICK_SECONDS", "10"))
    min_active_processes: int = int(os.getenv("SEGFAULT_MIN_ACTIVE_PROCESSES", "1"))
    empty_shard_ticks: int = int(os.getenv("SEGFAULT_EMPTY_SHARD_TICKS", "12"))
    random_seed: int = int(os.getenv("SEGFAULT_RANDOM_SEED", "42"))


settings = Settings()
