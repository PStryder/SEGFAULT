from __future__ import annotations

from dataclasses import dataclass, field

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
    last_sprint_tick: int = -999


@dataclass
class SayRecipient:
    process_id: str
    pos: Tile


@dataclass
class SayEvent:
    sender_id: str
    sender_pos: Tile
    message: str
    recipients: list[SayRecipient]
    timestamp_ms: int
    tick: int


@dataclass
class EchoTile:
    pos: Tile
    tick: int


@dataclass
class DefragmenterState:
    pos: Tile
    target_id: str | None = None
    target_reason: str | None = None  # broadcast | los | watchdog | patrol
    last_los_target_id: str | None = None
    target_acquired_tick: int | None = None


@dataclass
class WatchdogState:
    quiet_ticks: int = 0
    countdown: int = 0
    active: bool = False
    bonus_step: int = 0
    restored_this_tick: bool = False


@dataclass
class TickEvents:
    kills: list[str] = field(default_factory=list)
    survivals: list[str] = field(default_factory=list)
    ghosts: list[str] = field(default_factory=list)
    spawns: list[str] = field(default_factory=list)


@dataclass
class ShardState:
    shard_id: str
    walls: dict[int, WallEdge]
    gates: list[Gate]
    processes: dict[str, ProcessState]
    defragger: DefragmenterState
    broadcasts: list[Broadcast] = field(default_factory=list)
    last_broadcasts: list[Broadcast] = field(default_factory=list)
    say_events: list[SayEvent] = field(default_factory=list)
    echo_tiles: list[EchoTile] = field(default_factory=list)
    noise_burst_remaining: int = 0
    tick_events: TickEvents = field(default_factory=TickEvents)
    pending_spawns: list[str] = field(default_factory=list)
    total_processes: int = 0
    total_kills: int = 0
    total_survivals: int = 0
    total_ghosts: int = 0
    tick: int = 0
    watchdog: WatchdogState = field(default_factory=WatchdogState)
    empty_ticks: int = 0

    @property
    def walls_set(self):
        return set(self.walls.values())
