from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List


class Persistence(ABC):
    """Abstract persistence interface for leaderboard and logs."""

    @abstractmethod
    def record_survival(self, call_sign: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def record_death(self, call_sign: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def record_ghost(self, call_sign: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def leaderboard(self) -> List[Dict]:
        raise NotImplementedError

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
    def list_replay_shards(self, limit: int = 50) -> List[Dict]:
        raise NotImplementedError

    @abstractmethod
    def get_replay_ticks(
        self, shard_id: str, start_tick: int = 0, limit: int = 100
    ) -> List[Dict]:
        raise NotImplementedError
