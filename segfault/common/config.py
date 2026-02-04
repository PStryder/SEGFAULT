from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(value: str, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _parse_origins(value: str | None) -> list[str]:
    if not value:
        return ["*"]
    return [origin.strip() for origin in value.split(",") if origin.strip()]


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
    enable_tick_loop: bool = _env_bool(os.getenv("SEGFAULT_ENABLE_TICK_LOOP", "1"))
    cors_origins: list[str] = _parse_origins(os.getenv("SEGFAULT_CORS_ORIGINS"))


settings = Settings()
