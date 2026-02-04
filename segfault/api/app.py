from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from segfault.api.models import (
    CommandRequest,
    JoinResponse,
    ProcessStateResponse,
    SpectatorShardState,
)
from segfault.api.public_docs import PUBLIC_DOCS
from segfault.common.config import settings
from segfault.engine.engine import TickEngine
from segfault.persist.sqlite import SqlitePersistence

app = FastAPI(title="SEGFAULT")

logger = logging.getLogger(__name__)

persistence: SqlitePersistence | None = None
engine: TickEngine | None = None

# Chat connections
chat_clients: set[WebSocket] = set()
chat_clients_lock = asyncio.Lock()

# Spectator WS connections by shard id
spectator_clients: Dict[str, set[WebSocket]] = {}
spectator_clients_lock = asyncio.Lock()

# Leaderboard cache (delayed/batched updates)
leaderboard_cache: Dict[str, object] = {"data": [], "timestamp": 0}


def _get_engine() -> TickEngine:
    assert engine is not None
    return engine


def _get_persistence() -> SqlitePersistence:
    assert persistence is not None
    return persistence


@app.on_event("startup")
async def _startup() -> None:
    global persistence, engine
    persistence = SqlitePersistence(settings.db_path)
    engine = TickEngine(
        persistence,
        seed=settings.random_seed,
        min_active_processes=settings.min_active_processes,
        empty_shard_ticks=settings.empty_shard_ticks,
    )
    engine.create_shard()
    asyncio.create_task(tick_loop())


async def tick_loop() -> None:
    game_engine = _get_engine()
    while True:
        game_engine.tick_once()
        # broadcast spectator snapshots
        async with spectator_clients_lock:
            shard_clients = [(sid, list(clients)) for sid, clients in spectator_clients.items()]
        for shard_id, clients in shard_clients:
            state = game_engine.render_spectator_view(shard_id)
            stale: List[WebSocket] = []
            for ws in clients:
                try:
                    await ws.send_json(state)
                except Exception:
                    logger.exception("Failed to send spectator update")
                    stale.append(ws)
            if stale:
                async with spectator_clients_lock:
                    live_clients = spectator_clients.get(shard_id)
                    if live_clients:
                        for ws in stale:
                            live_clients.discard(ws)
                        if not live_clients:
                            spectator_clients.pop(shard_id, None)
        await asyncio.sleep(settings.tick_seconds)


@app.post("/process/join", response_model=JoinResponse)
def join_process() -> JoinResponse:
    game_engine = _get_engine()
    token, process_id = game_engine.join_process()
    return JoinResponse(token=token, process_id=process_id)


@app.get("/process/state", response_model=ProcessStateResponse)
def process_state(token: str) -> ProcessStateResponse:
    game_engine = _get_engine()
    process_id = game_engine.session_tokens.get(token)
    if not process_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    data = game_engine.render_process_view(process_id)
    return ProcessStateResponse(**data)


@app.post("/process/cmd")
def process_cmd(token: str, req: CommandRequest) -> Dict[str, str]:
    game_engine = _get_engine()
    process_id = game_engine.session_tokens.get(token)
    if not process_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    cmd = req.cmd.upper()
    if cmd not in {"MOVE", "BUFFER", "BROADCAST", "IDLE", "SAY"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid command")
    game_engine.buffer_command(process_id, command_request_to_command(req))
    return {"status": "ok"}


def command_request_to_command(req: CommandRequest):
    from segfault.common.types import Command, CommandType

    cmd = CommandType(req.cmd.upper())
    return Command(cmd=cmd, arg=req.arg)


@app.get("/process/info")
def process_info() -> Dict[str, object]:
    return PUBLIC_DOCS


@app.get("/spectate/shards")
def list_shards() -> List[Dict]:
    game_engine = _get_engine()
    return [
        {
            "shard_id": shard.shard_id,
            "process_count": len(shard.processes),
            "tick": shard.tick,
        }
        for shard in game_engine.shards.values()
    ]


@app.get("/spectate/shard/{shard_id}", response_model=SpectatorShardState)
def spectate_shard(shard_id: str) -> SpectatorShardState:
    game_engine = _get_engine()
    data = game_engine.render_spectator_view(shard_id)
    return SpectatorShardState(**data)


@app.get("/leaderboard")
def leaderboard() -> Response | Dict[str, object]:
    store = _get_persistence()
    now = int(time.time())
    if now - int(leaderboard_cache["timestamp"]) > 30:
        leaderboard_cache["data"] = store.leaderboard()
        leaderboard_cache["timestamp"] = now
    entries = leaderboard_cache["data"]
    if not entries:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return {"entries": entries}


@app.websocket("/spectate/ws/{shard_id}")
async def spectate_ws(ws: WebSocket, shard_id: str) -> None:
    await ws.accept()
    async with spectator_clients_lock:
        spectator_clients.setdefault(shard_id, set()).add(ws)
    try:
        while True:
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                logger.exception("Spectator websocket receive failed")
                break
    finally:
        async with spectator_clients_lock:
            clients = spectator_clients.get(shard_id)
            if clients:
                clients.discard(ws)
                if not clients:
                    spectator_clients.pop(shard_id, None)


@app.websocket("/chat/ws")
async def chat_ws(ws: WebSocket) -> None:
    await ws.accept()
    async with chat_clients_lock:
        chat_clients.add(ws)
    try:
        while True:
            try:
                msg = await ws.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                logger.exception("Chat websocket receive failed")
                break
            msg = msg[:256]
            payload = {
                "author": "spectator",
                "message": msg,
                "timestamp_ms": int(time.time() * 1000),
            }
            async with chat_clients_lock:
                clients = list(chat_clients)
            stale: List[WebSocket] = []
            for client in clients:
                try:
                    await client.send_json(payload)
                except Exception:
                    logger.exception("Chat websocket send failed")
                    stale.append(client)
            if stale:
                async with chat_clients_lock:
                    for client in stale:
                        chat_clients.discard(client)
    finally:
        async with chat_clients_lock:
            chat_clients.discard(ws)


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
