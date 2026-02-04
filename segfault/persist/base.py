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
