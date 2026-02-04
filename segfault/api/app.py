from __future__ import annotations

import asyncio
import time
from typing import Dict, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from segfault.api.models import CommandRequest, JoinResponse, ProcessStateResponse, SpectatorShardState
from segfault.common.config import settings
from segfault.engine.engine import TickEngine
from segfault.persist.sqlite import SqlitePersistence

app = FastAPI(title="SEGFAULT")

persistence = SqlitePersistence(settings.db_path)
engine = TickEngine(
    persistence,
    seed=settings.random_seed,
    min_active_processes=settings.min_active_processes,
    empty_shard_ticks=settings.empty_shard_ticks,
)

# Ensure at least one shard exists
engine.create_shard()

# Chat connections
chat_clients: List[WebSocket] = []

# Spectator WS connections by shard id
spectator_clients: Dict[str, List[WebSocket]] = {}

# Leaderboard cache (delayed/batched updates)
leaderboard_cache: Dict[str, object] = {"data": [], "timestamp": 0}


@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(tick_loop())


async def tick_loop() -> None:
    while True:
        engine.tick_once()
        # broadcast spectator snapshots
        for shard_id, clients in list(spectator_clients.items()):
            state = engine.render_spectator_view(shard_id)
            for ws in list(clients):
                try:
                    await ws.send_json(state)
                except Exception:
                    clients.remove(ws)
        await asyncio.sleep(settings.tick_seconds)


@app.post("/process/join", response_model=JoinResponse)
def join_process() -> JoinResponse:
    token, process_id = engine.join_process()
    return JoinResponse(token=token, process_id=process_id)


@app.get("/process/state", response_model=ProcessStateResponse)
def process_state(token: str) -> ProcessStateResponse:
    process_id = engine.session_tokens.get(token)
    if not process_id:
        return ProcessStateResponse(tick=0, grid="", events=[])
    data = engine.render_process_view(process_id)
    return ProcessStateResponse(**data)


@app.post("/process/cmd")
def process_cmd(token: str, req: CommandRequest) -> Dict[str, str]:
    process_id = engine.session_tokens.get(token)
    if not process_id:
        return {"status": "invalid"}
    cmd = req.cmd.upper()
    if cmd not in {"MOVE", "BUFFER", "BROADCAST", "IDLE"}:
        return {"status": "invalid"}
    engine.buffer_command(process_id, CommandRequestToCommand(req))
    return {"status": "ok"}


def CommandRequestToCommand(req: CommandRequest):
    from segfault.common.types import Command, CommandType

    cmd = CommandType(req.cmd.upper())
    return Command(cmd=cmd, arg=req.arg)


@app.get("/spectate/shards")
def list_shards() -> List[Dict]:
    return [
        {
            "shard_id": shard.shard_id,
            "process_count": len(shard.processes),
            "tick": shard.tick,
        }
        for shard in engine.shards.values()
    ]


@app.get("/spectate/shard/{shard_id}", response_model=SpectatorShardState)
def spectate_shard(shard_id: str) -> SpectatorShardState:
    data = engine.render_spectator_view(shard_id)
    return SpectatorShardState(**data)


@app.get("/leaderboard")
def leaderboard() -> Dict[str, object]:
    now = int(time.time())
    if now - int(leaderboard_cache["timestamp"]) > 30:
        leaderboard_cache["data"] = persistence.leaderboard()
        leaderboard_cache["timestamp"] = now
    return {"entries": leaderboard_cache["data"]}


@app.websocket("/spectate/ws/{shard_id}")
async def spectate_ws(ws: WebSocket, shard_id: str) -> None:
    await ws.accept()
    spectator_clients.setdefault(shard_id, []).append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        spectator_clients[shard_id].remove(ws)


@app.websocket("/chat/ws")
async def chat_ws(ws: WebSocket) -> None:
    await ws.accept()
    chat_clients.append(ws)
    try:
        while True:
            msg = await ws.receive_text()
            payload = {
                "author": "spectator",
                "message": msg,
                "timestamp_ms": int(time.time() * 1000),
            }
            for client in list(chat_clients):
                try:
                    await client.send_json(payload)
                except Exception:
                    chat_clients.remove(client)
    except WebSocketDisconnect:
        chat_clients.remove(ws)


# Static web UI
app.mount("/static", StaticFiles(directory="segfault/web/static"), name="static")


@app.get("/")
def home() -> FileResponse:
    return FileResponse("segfault/web/index.html")


@app.get("/process")
def process_ui() -> FileResponse:
    return FileResponse("segfault/web/process.html")


@app.get("/spectate")
def spectator_ui() -> FileResponse:
    return FileResponse("segfault/web/spectate.html")


@app.get("/donate")
def donate_placeholder() -> FileResponse:
    return FileResponse("segfault/web/donate.html")


@app.get("/adblock")
def adblock_placeholder() -> FileResponse:
    return FileResponse("segfault/web/adblock.html")
