from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from segfault.api.models import (
    CommandRequest,
    JoinResponse,
    ProcessStateResponse,
    ReplayResponse,
    ReplayShardSummary,
    SpectatorShardState,
)
from segfault.api.public_docs import PUBLIC_DOCS
from segfault.common.config import settings
from segfault.engine.engine import TickEngine
from segfault.persist.sqlite import SqlitePersistence

app = FastAPI(title="SEGFAULT")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)

SPECTATOR_SEND_TIMEOUT = 1.0
FLAVOR_CHANNELS = {"proc", "spec", "sys"}

persistence: SqlitePersistence | None = None
engine: TickEngine | None = None
tick_stop = asyncio.Event()
tick_task: asyncio.Task | None = None

# Chat connections
chat_clients: set[WebSocket] = set()
chat_clients_lock = asyncio.Lock()

# Spectator WS connections by shard id
spectator_clients: dict[str, set[WebSocket]] = {}
spectator_clients_lock = asyncio.Lock()


@dataclass
class ShardBroadcaster:
    queue: asyncio.Queue[dict[str, object]]
    task: asyncio.Task


spectator_broadcasters: dict[str, ShardBroadcaster] = {}

# Leaderboard cache (delayed/batched updates)
leaderboard_cache: dict[str, object] = {"data": [], "timestamp": 0}
leaderboard_lock = asyncio.Lock()
engine_lock = asyncio.Lock()
rate_limit_lock = asyncio.Lock()
cmd_rate: dict[str, tuple[int, float]] = {}
join_rate_lock = asyncio.Lock()
join_rate: dict[str, tuple[int, float]] = {}


def _get_engine() -> TickEngine:
    assert engine is not None
    return engine


def _get_persistence() -> SqlitePersistence:
    assert persistence is not None
    return persistence


def _extract_token(token: str | None, authorization: str | None) -> str | None:
    if authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
        return authorization.strip()
    return token


def _check_api_key(provided: str | None) -> None:
    if settings.api_key and provided != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def _is_allowed_origin(origin: str | None) -> bool:
    if not origin:
        return True
    allowed = [o.rstrip("/") for o in settings.cors_origins]
    return origin.rstrip("/") in allowed


def _prune_rate_limit(
    store: dict[str, tuple[int, float]], window_seconds: float, now: float
) -> None:
    if len(store) < 5000:
        return
    cutoff = now - max(window_seconds * 2, 10.0)
    for key, (_, start) in list(store.items()):
        if start < cutoff:
            store.pop(key, None)


async def _check_rate_limit(token: str) -> None:
    limit = settings.cmd_rate_limit
    if limit <= 0:
        return
    now = time.monotonic()
    async with rate_limit_lock:
        count, start = cmd_rate.get(token, (0, now))
        if now - start >= settings.cmd_rate_window_seconds:
            count = 0
            start = now
        count += 1
        cmd_rate[token] = (count, start)
        _prune_rate_limit(cmd_rate, settings.cmd_rate_window_seconds, now)
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded"
            )


async def _check_join_rate(ip: str | None) -> None:
    limit = settings.join_rate_limit
    if limit <= 0 or not ip:
        return
    now = time.monotonic()
    async with join_rate_lock:
        count, start = join_rate.get(ip, (0, now))
        if now - start >= settings.join_rate_window_seconds:
            count = 0
            start = now
        count += 1
        join_rate[ip] = (count, start)
        _prune_rate_limit(join_rate, settings.join_rate_window_seconds, now)
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Join rate limit exceeded"
            )


@app.on_event("startup")
async def _startup() -> None:
    global persistence, engine, tick_task
    persistence = SqlitePersistence(settings.db_path, replay_compress=settings.replay_compress)
    if persistence.flavor_count() == 0:
        flavor_path = Path(__file__).resolve().parents[1] / "lore" / "flavor.md"
        inserted = persistence.seed_flavor_from_markdown(str(flavor_path))
        logger.info("Seeded %s flavor lines", inserted)
    engine = TickEngine(
        persistence,
        seed=settings.random_seed,
        min_active_processes=settings.min_active_processes,
        empty_shard_ticks=settings.empty_shard_ticks,
        max_total_processes=settings.max_total_processes,
        enable_replay_logging=settings.enable_replay_logging,
    )
    engine.create_shard()
    if settings.enable_tick_loop:
        tick_task = asyncio.create_task(tick_loop(tick_stop))
    else:
        logger.warning("Tick loop disabled via SEGFAULT_ENABLE_TICK_LOOP")


@app.on_event("shutdown")
async def _shutdown() -> None:
    tick_stop.set()
    if tick_task:
        try:
            await asyncio.wait_for(tick_task, timeout=2.0)
        except TimeoutError:
            tick_task.cancel()
        except Exception:
            tick_task.cancel()
    if persistence is not None:
        persistence.close()


async def tick_loop(stop_event: asyncio.Event) -> None:
    game_engine = _get_engine()
    while not stop_event.is_set():
        # enqueue spectator snapshots (per-shard broadcasters drop stale frames)
        async with spectator_clients_lock:
            shard_queues = {
                shard_id: broadcaster.queue
                for shard_id, broadcaster in spectator_broadcasters.items()
            }
        shard_ids = list(shard_queues.keys())
        async with engine_lock:
            game_engine.tick_once()
            shard_states = {
                shard_id: game_engine.render_spectator_view(shard_id) for shard_id in shard_ids
            }
        for shard_id, queue in shard_queues.items():
            state = shard_states.get(shard_id)
            if not state:
                continue
            _queue_latest(queue, state)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.tick_seconds)
        except TimeoutError:
            pass


def _queue_latest(queue: asyncio.Queue[dict[str, object]], state: dict[str, object]) -> None:
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


async def _send_spectator_state(ws: WebSocket, state: dict[str, object]) -> bool:
    try:
        await asyncio.wait_for(ws.send_json(state), timeout=SPECTATOR_SEND_TIMEOUT)
        return True
    except Exception:
        logger.exception("Failed to send spectator update")
        return False


async def _ws_keepalive(ws: WebSocket, interval: float = 30.0) -> None:
    while True:
        try:
            await asyncio.sleep(interval)
            await ws.send_json({"type": "ping"})
        except Exception:
            break


async def _broadcast_shard(shard_id: str, queue: asyncio.Queue[dict[str, object]]) -> None:
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
        stale = [ws for ws, ok in zip(clients, results, strict=False) if ok is not True]
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
async def join_process(
    request: Request, x_api_key: str | None = Header(default=None)
) -> JoinResponse:
    _check_api_key(x_api_key)
    ip = request.client.host if request.client else None
    await _check_join_rate(ip)
    game_engine = _get_engine()
    async with engine_lock:
        result = game_engine.join_process()
    if not result:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Server full")
    token, process_id = result
    return JoinResponse(token=token, process_id=process_id)


@app.get("/process/state", response_model=ProcessStateResponse)
async def process_state(
    token: str | None = None,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> ProcessStateResponse:
    _check_api_key(x_api_key)
    resolved = _extract_token(token, authorization)
    if not resolved:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    game_engine = _get_engine()
    async with engine_lock:
        process_id = game_engine.resolve_token(resolved, settings.token_ttl_seconds)
        if not process_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        data = game_engine.render_process_view(process_id)
    return ProcessStateResponse(**data)


@app.post("/process/cmd")
async def process_cmd(
    req: CommandRequest,
    token: str | None = None,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> dict[str, str]:
    _check_api_key(x_api_key)
    resolved = _extract_token(token, authorization)
    if not resolved:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    await _check_rate_limit(resolved)
    game_engine = _get_engine()
    async with engine_lock:
        process_id = game_engine.resolve_token(resolved, settings.token_ttl_seconds)
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
async def process_info() -> dict[str, object]:
    return PUBLIC_DOCS


@app.get("/flavor/random")
async def flavor_random(
    channel: str | None = None, x_api_key: str | None = Header(default=None)
) -> Response | dict[str, str]:
    _check_api_key(x_api_key)
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
async def list_shards(x_api_key: str | None = Header(default=None)) -> list[dict]:
    _check_api_key(x_api_key)
    game_engine = _get_engine()
    async with engine_lock:
        shards = list(game_engine.shards.values())
    return [
        {
            "shard_id": shard.shard_id,
            "process_count": len(shard.processes),
            "tick": shard.tick,
        }
        for shard in shards
    ]


@app.get("/spectate/shard/{shard_id}", response_model=SpectatorShardState)
async def spectate_shard(
    shard_id: str, x_api_key: str | None = Header(default=None)
) -> SpectatorShardState:
    _check_api_key(x_api_key)
    game_engine = _get_engine()
    async with engine_lock:
        data = game_engine.render_spectator_view(shard_id)
    return SpectatorShardState(**data)


@app.get("/leaderboard")
async def leaderboard(x_api_key: str | None = Header(default=None)) -> Response | dict[str, object]:
    _check_api_key(x_api_key)
    store = _get_persistence()
    async with leaderboard_lock:
        now = int(time.time())
        if now - int(leaderboard_cache["timestamp"]) > settings.leaderboard_cache_seconds:
            leaderboard_cache["data"] = store.leaderboard()
            leaderboard_cache["timestamp"] = now
        entries = leaderboard_cache["data"]
    if not entries:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return {"entries": entries}


@app.get("/replays", response_model=dict[str, list[ReplayShardSummary]])
async def list_replays(
    limit: int = 50, x_api_key: str | None = Header(default=None)
) -> dict[str, list[ReplayShardSummary]]:
    _check_api_key(x_api_key)
    store = _get_persistence()
    capped = max(1, min(limit, 200))
    shards = store.list_replay_shards(capped)
    return {"shards": shards}


@app.get("/replays/{shard_id}", response_model=ReplayResponse)
async def replay_detail(
    shard_id: str,
    start_tick: int = 0,
    limit: int = 100,
    x_api_key: str | None = Header(default=None),
) -> ReplayResponse:
    _check_api_key(x_api_key)
    store = _get_persistence()
    capped = max(1, min(limit, 500))
    ticks = store.get_replay_ticks(shard_id, start_tick=start_tick, limit=capped + 1)
    has_more = len(ticks) > capped
    if has_more:
        ticks = ticks[:capped]
    return ReplayResponse(shard_id=shard_id, ticks=ticks, has_more=has_more)


@app.websocket("/spectate/ws/{shard_id}")
async def spectate_ws(ws: WebSocket, shard_id: str, key: str | None = None) -> None:
    _check_api_key(key)
    if not _is_allowed_origin(ws.headers.get("origin")):
        await ws.accept()
        await ws.close(code=1008)
        return
    await ws.accept()
    async with spectator_clients_lock:
        spectator_clients.setdefault(shard_id, set()).add(ws)
        if shard_id not in spectator_broadcasters:
            queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=1)
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
async def chat_ws(ws: WebSocket, key: str | None = None) -> None:
    _check_api_key(key)
    if not _is_allowed_origin(ws.headers.get("origin")):
        await ws.accept()
        await ws.close(code=1008)
        return
    await ws.accept()
    async with chat_clients_lock:
        chat_clients.add(ws)
    keepalive = asyncio.create_task(_ws_keepalive(ws))
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
            stale: list[WebSocket] = []
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
        keepalive.cancel()
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
    return FileResponse("segfault/web/spectator.html")


@app.get("/spectator")
def spectator_ui_alias() -> FileResponse:
    return FileResponse("segfault/web/spectator.html")


@app.get("/spectator/profile")
def spectator_profile_ui() -> FileResponse:
    return FileResponse("segfault/web/spectator-profile.html")


@app.get("/spectator/queue")
def spectator_queue_ui() -> FileResponse:
    return FileResponse("segfault/web/spectator-queue.html")


@app.get("/replay")
def replay_ui() -> FileResponse:
    return FileResponse("segfault/web/replay.html")


@app.get("/donate")
def donate_placeholder() -> FileResponse:
    return FileResponse("segfault/web/donate.html")


@app.get("/adblock")
def adblock_placeholder() -> FileResponse:
    return FileResponse("segfault/web/adblock.html")


@app.get("/SKILL.md")
def skill_markdown() -> FileResponse:
    return FileResponse("segfault/web/SKILL.md", media_type="text/markdown")
