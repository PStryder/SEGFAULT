from __future__ import annotations

from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


class JoinResponse(BaseModel):
    token: str
    process_id: str


class CommandRequest(BaseModel):
    cmd: str
    arg: Optional[str] = None


class ProcessStateResponse(BaseModel):
    tick: int
    grid: str
    events: List[dict]


class SpectatorShardSummary(BaseModel):
    shard_id: str
    process_count: int
    tick: int


class SpectatorShardState(BaseModel):
    tick: int
    grid: List[List[str]]
    defragger: Tuple[int, int]
    defragger_target: Optional[dict] = None
    defragger_preview: List[Tuple[int, int]] = Field(default_factory=list)
    walls: List[dict] = Field(default_factory=list)
    gates: List[dict]
    processes: List[dict]
    watchdog: dict
    say_events: List[dict] = Field(default_factory=list)
    echo_tiles: List[dict] = Field(default_factory=list)


class ChatMessage(BaseModel):
    author: str
    message: str
    timestamp_ms: int


class ReplayShardSummary(BaseModel):
    shard_id: str
    started_at: int
    ended_at: int | None = None
    total_ticks: int
    total_processes: int
    total_kills: int
    total_survivals: int
    total_ghosts: int


class ReplayTickEntry(BaseModel):
    tick: int
    snapshot: dict


class ReplayResponse(BaseModel):
    shard_id: str
    ticks: List[ReplayTickEntry]
    has_more: bool
