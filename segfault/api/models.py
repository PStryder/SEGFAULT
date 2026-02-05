from __future__ import annotations

from pydantic import BaseModel, Field


class JoinResponse(BaseModel):
    token: str
    process_id: str


class CommandRequest(BaseModel):
    cmd: str
    arg: str | None = None


class ProcessStateResponse(BaseModel):
    tick: int
    grid: str
    events: list[dict]


class SpectatorShardSummary(BaseModel):
    shard_id: str
    process_count: int
    tick: int


class SpectatorShardState(BaseModel):
    tick: int
    grid: list[list[str]]
    defragger: tuple[int, int]
    defragger_target: dict | None = None
    defragger_preview: list[tuple[int, int]] = Field(default_factory=list)
    walls: list[dict] = Field(default_factory=list)
    gates: list[dict]
    processes: list[dict]
    watchdog: dict
    say_events: list[dict] = Field(default_factory=list)
    echo_tiles: list[dict] = Field(default_factory=list)


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
    ticks: list[ReplayTickEntry]
    has_more: bool
