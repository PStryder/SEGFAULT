from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

Tile = Tuple[int, int]
Point = Tuple[float, float]
Edge = Tuple[Point, Point]


class GateType(str, Enum):
    STABLE = "stable"
    GHOST = "ghost"


class CommandType(str, Enum):
    MOVE = "MOVE"
    BUFFER = "BUFFER"
    BROADCAST = "BROADCAST"
    IDLE = "IDLE"
    SAY = "SAY"


@dataclass(frozen=True)
class Command:
    cmd: CommandType
    arg: str | None = None


@dataclass(frozen=True)
class Broadcast:
    process_id: str
    message: str
    timestamp_ms: int
