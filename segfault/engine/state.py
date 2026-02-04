from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from segfault.common.constants import GRID_SIZE
from segfault.common.types import Broadcast, Command, CommandType, GateType, Tile
from segfault.engine.geometry import WallEdge


@dataclass
class Gate:
    gate_type: GateType
    pos: Tile


@dataclass
class ProcessState:
    process_id: str
    call_sign: str
    pos: Tile
    buffered: Command = field(default_factory=lambda: Command(CommandType.IDLE))
    alive: bool = True
    los_lock: bool = False


@dataclass
class SayRecipient:
    process_id: str
    pos: Tile


@dataclass
class SayEvent:
    sender_id: str
    sender_pos: Tile
    message: str
    recipients: List[SayRecipient]
    timestamp_ms: int


@dataclass
class DefragmenterState:
    pos: Tile
    target_id: Optional[str] = None
    target_reason: Optional[str] = None  # broadcast | los | patrol


@dataclass
class WatchdogState:
    quiet_ticks: int = 0
    countdown: int = 0
    active: bool = False
    bonus_step: int = 0
    restored_this_tick: bool = False


@dataclass
class ShardState:
    shard_id: str
    walls: Dict[int, WallEdge]
    gates: List[Gate]
    processes: Dict[str, ProcessState]
    defragger: DefragmenterState
    broadcasts: List[Broadcast] = field(default_factory=list)
    say_events: List[SayEvent] = field(default_factory=list)
    tick: int = 0
    watchdog: WatchdogState = field(default_factory=WatchdogState)
    empty_ticks: int = 0

    @property
    def walls_set(self):
        return set(self.walls.values())
