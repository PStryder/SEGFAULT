from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
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

SPECTATOR_SEND_TIMEOUT = 1.0
FLAVOR_CHANNELS = {"proc", "spec", "sys"}

persistence: SqlitePersistence | None = None
engine: TickEngine | None = None

# Chat connections
chat_clients: set[WebSocket] = set()
chat_clients_lock = asyncio.Lock()

# Spectator WS connections by shard id
spectator_clients: Dict[str, set[WebSocket]] = {}
spectator_clients_lock = asyncio.Lock()


@dataclass
class ShardBroadcaster:
    queue: asyncio.Queue[Dict[str, object]]
    task: asyncio.Task


spectator_broadcasters: Dict[str, ShardBroadcaster] = {}

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
    if persistence.flavor_count() == 0:
        flavor_path = Path(__file__).resolve().parents[1] / "lore" / "flavor.md"
        inserted = persistence.seed_flavor_from_markdown(str(flavor_path))
        logger.info("Seeded %s flavor lines", inserted)
    engine = TickEngine(
        persistence,
        seed=settings.random_seed,
        min_active_processes=settings.min_active_processes,
        empty_shard_ticks=settings.empty_shard_ticks,
    )
    engine.create_shard()
    if settings.enable_tick_loop:
        asyncio.create_task(tick_loop())
    else:
        logger.warning("Tick loop disabled via SEGFAULT_ENABLE_TICK_LOOP")


@app.on_event("shutdown")
async def _shutdown() -> None:
    if persistence is not None:
        persistence.close()


async def tick_loop() -> None:
    game_engine = _get_engine()
    while True:
        game_engine.tick_once()
        # enqueue spectator snapshots (per-shard broadcasters drop stale frames)
        async with spectator_clients_lock:
            shard_queues = {
                shard_id: broadcaster.queue
                for shard_id, broadcaster in spectator_broadcasters.items()
            }
        for shard_id, queue in shard_queues.items():
            state = game_engine.render_spectator_view(shard_id)
            if not state:
                continue
            _queue_latest(queue, state)
        await asyncio.sleep(settings.tick_seconds)


def _queue_latest(queue: asyncio.Queue[Dict[str, object]], state: Dict[str, object]) -> None:
    try:
        queue.put_nowait(state)
    except asyncio.QueueFull:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(state)
        except asyncio.QueueFull:
            pass


async def _send_spectator_state(ws: WebSocket, state: Dict[str, object]) -> bool:
    try:
        await asyncio.wait_for(ws.send_json(state), timeout=SPECTATOR_SEND_TIMEOUT)
        return True
    except Exception:
        logger.exception("Failed to send spectator update")
        return False


async def _broadcast_shard(shard_id: str, queue: asyncio.Queue[Dict[str, object]]) -> None:
    while True:
        try:
            state = await queue.get()
        except asyncio.CancelledError:
            break
        async with spectator_clients_lock:
            clients = list(spectator_clients.get(shard_id, set()))
        if not clients:
            continue
        results = await asyncio.gather(
            *(_send_spectator_state(ws, state) for ws in clients),
            return_exceptions=True,
        )
        stale = [ws for ws, ok in zip(clients, results) if ok is not True]
        if stale:
            async with spectator_clients_lock:
                live_clients = spectator_clients.get(shard_id)
                if live_clients:
                    for ws in stale:
                        live_clients.discard(ws)
                    if not live_clients:
                        spectator_clients.pop(shard_id, None)
                        broadcaster = spectator_broadcasters.pop(shard_id, None)
                        if broadcaster:
                            broadcaster.task.cancel()


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


@app.get("/flavor/random")
def flavor_random(channel: str | None = None) -> Response | Dict[str, str]:
    store = _get_persistence()
    if channel:
        channel = channel.lower()
        if channel not in FLAVOR_CHANNELS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid channel")
        entry = store.random_flavor(channel)
        if not entry:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        return entry
    entry = store.random_flavor()
    if not entry:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return entry


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
        if shard_id not in spectator_broadcasters:
            queue: asyncio.Queue[Dict[str, object]] = asyncio.Queue(maxsize=1)
            task = asyncio.create_task(_broadcast_shard(shard_id, queue))
            spectator_broadcasters[shard_id] = ShardBroadcaster(queue=queue, task=task)
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
                    broadcaster = spectator_broadcasters.pop(shard_id, None)
                    if broadcaster:
                        broadcaster.task.cancel()


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
