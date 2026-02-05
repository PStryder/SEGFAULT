from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(value: str, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _parse_origins(value: str | None) -> list[str]:
    if not value:
        return [
            "https://segfault.pstryder.com",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
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
    cors_origins: list[str] = field(
        default_factory=lambda: _parse_origins(os.getenv("SEGFAULT_CORS_ORIGINS"))
    )
    cmd_rate_limit: int = int(os.getenv("SEGFAULT_CMD_RATE_LIMIT", "20"))
    cmd_rate_window_seconds: float = float(os.getenv("SEGFAULT_CMD_RATE_WINDOW", "1.0"))
    join_rate_limit: int = int(os.getenv("SEGFAULT_JOIN_RATE_LIMIT", "10"))
    join_rate_window_seconds: float = float(os.getenv("SEGFAULT_JOIN_RATE_WINDOW", "60"))
    max_total_processes: int = int(os.getenv("SEGFAULT_MAX_TOTAL_PROCESSES", "1000"))
    token_ttl_seconds: int = int(os.getenv("SEGFAULT_TOKEN_TTL_SECONDS", "3600"))
    leaderboard_cache_seconds: int = int(os.getenv("SEGFAULT_LEADERBOARD_CACHE_SECONDS", "300"))
    enable_replay_logging: bool = _env_bool(os.getenv("SEGFAULT_REPLAY_LOGGING", "1"))
    replay_compress: bool = _env_bool(os.getenv("SEGFAULT_REPLAY_COMPRESS", "0"))
    replay_max_ticks: int = int(os.getenv("SEGFAULT_REPLAY_MAX_TICKS", "0"))
    replay_max_shards: int = int(os.getenv("SEGFAULT_REPLAY_MAX_SHARDS", "0"))
    ws_allow_any_origin: bool = _env_bool(os.getenv("SEGFAULT_WS_ALLOW_ANY_ORIGIN", "0"))
    api_key: str | None = os.getenv("SEGFAULT_API_KEY")


settings = Settings()
