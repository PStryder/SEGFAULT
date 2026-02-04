from __future__ import annotations

from typing import List, Optional, Tuple

from pydantic import BaseModel


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
    gates: List[dict]
    processes: List[dict]
    watchdog: dict
    say_events: List[dict] = []


class ChatMessage(BaseModel):
    author: str
    message: str
    timestamp_ms: int
