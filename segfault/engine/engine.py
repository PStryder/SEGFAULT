from __future__ import annotations

import random
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from segfault.common.constants import (
    FIBONACCI_ESCALATION,
    GRID_SIZE,
    MAX_PROCESSES_PER_SHARD,
    QUIET_TICKS_WARNING,
    WATCHDOG_COUNTDOWN,
)
from segfault.common.types import Broadcast, Command, CommandType, GateType, Tile
from segfault.engine.drift import drift_gates, drift_walls
from segfault.engine.geometry import (
    adjacent_tiles,
    diagonal_legal,
    edge_slots,
    in_bounds,
    los_clear,
    neighbors_8,
    wall_blocks,
    WallEdge,
)
from segfault.engine.state import (
    DefragmenterState,
    EchoTile,
    Gate,
    ProcessState,
    SayEvent,
    SayRecipient,
    ShardState,
    WatchdogState,
)
from segfault.persist.base import Persistence

DIRECTION_MAP = {
    1: (-1, -1),
    2: (0, -1),
    3: (1, -1),
    4: (-1, 0),
    5: (0, 0),
    6: (1, 0),
    7: (-1, 1),
    8: (0, 1),
    9: (1, 1),
}

CHAT_ARTIFACT_PROB = 0.015
CHAT_ARTIFACTS = ("...", "[STATIC]")
SAY_EVENT_TTL_TICKS = 3
ECHO_TTL_TICKS = 4
SPRINT_COOLDOWN_TICKS = 1
DEFRAGGER_WANDER_PROB = 0.15


@dataclass
class Event:
    kind: str
    message: str
    timestamp_ms: int


class TickEngine:
    """Authoritative tick engine managing multiple shards."""

    def __init__(
        self,
        persistence: Persistence,
        seed: int = 42,
        min_active_processes: int = 1,
        empty_shard_ticks: int = 12,
        max_total_processes: int | None = None,
    ) -> None:
        self.persistence = persistence
        self.rng = random.Random(seed)
        self.min_active_processes = min_active_processes
        self.empty_shard_ticks = empty_shard_ticks
        self.max_total_processes = max_total_processes
        self.shards: Dict[str, ShardState] = {}
        self.process_to_shard: Dict[str, str] = {}
        self.session_tokens: Dict[str, Tuple[str, int]] = {}
        self.process_events: Dict[str, List[Event]] = {}

    def create_shard(self) -> ShardState:
        """Create and register a new shard with walls, gates, and a defragmenter."""
        shard_id = str(uuid.uuid4())
        walls = self._generate_walls()
        gates = self._generate_gates(walls)
        defragger_pos = self._random_empty_tile(set(), {g.pos for g in gates})
        shard = ShardState(
            shard_id=shard_id,
            walls=walls,
            gates=gates,
            processes={},
            defragger=DefragmenterState(pos=defragger_pos),
        )
        self.shards[shard_id] = shard
        return shard

    def join_process(self) -> Tuple[str, str] | None:
        """Spawn a new process in a shard and return its session token and process id."""
        if self.max_total_processes is not None:
            if self._total_processes() >= self.max_total_processes:
                return None
        shard = self._find_or_create_shard()
        process_id = str(uuid.uuid4())
        call_sign = self._random_call_sign()
        pos = self._random_empty_tile(
            {p.pos for p in shard.processes.values()},
            {g.pos for g in shard.gates} | {shard.defragger.pos},
        )
        proc = ProcessState(process_id=process_id, call_sign=call_sign, pos=pos)
        shard.processes[process_id] = proc
        self.process_to_shard[process_id] = shard.shard_id
        self.process_events[process_id] = []
        token = str(uuid.uuid4())
        self.session_tokens[token] = (process_id, int(time.time()))
        return token, process_id

    def resolve_token(self, token: str, ttl_seconds: int | None = None) -> str | None:
        entry = self.session_tokens.get(token)
        if not entry:
            return None
        process_id, issued_at = entry
        if ttl_seconds and ttl_seconds > 0:
            if int(time.time()) - issued_at > ttl_seconds:
                self.session_tokens.pop(token, None)
                return None
        return process_id

    def buffer_command(self, process_id: str, cmd: Command) -> None:
        """Buffer the last valid command for a process (broadcasts are immediate)."""
        shard = self._get_shard_for_process(process_id)
        if not shard:
            return
        proc = shard.processes.get(process_id)
        if not proc or not proc.alive:
            return
        if cmd.cmd == CommandType.BROADCAST and cmd.arg:
            self._handle_broadcast(shard, process_id, cmd.arg[:256])
            return
        if cmd.cmd == CommandType.SAY and cmd.arg:
            self._handle_local_chat(shard, process_id, cmd.arg[:256])
            return
        proc.buffered = cmd

    def tick_once(self) -> None:
        """Advance all shards by a single tick."""
        for shard in list(self.shards.values()):
            self._tick_shard(shard)

    def _tick_shard(self, shard: ShardState) -> None:
        shard.tick += 1
        # Liveness restored if any process starts adjacent to defragger
        if any(
            _is_adjacent(p.pos, shard.defragger.pos, shard)
            for p in shard.processes.values()
            if p.alive
        ):
            self._reset_watchdog_on_liveness(shard, reason="adjacent")
        # Step 1: process actions resolve (pre-drift topology)
        moves = self._resolve_process_actions(shard)
        self._apply_process_moves(shard, moves)
        # Gate interactions resolve pre-drift
        self._resolve_gate_interactions(shard)
        # Step 2: drift
        drift_walls(shard, self.rng)
        drift_gates(shard, self.rng)
        # Step 3: defragger movement (post-drift)
        self._resolve_defragger(shard)
        # Watchdog progression if no liveness restored this tick
        self._advance_watchdog(shard)
        # Trim SAY traces after tick advancement
        self._trim_old_say_events(shard)
        self._trim_old_echo_tiles(shard)
        # Clear broadcasts for this tick window
        shard.broadcasts.clear()
        shard.watchdog.restored_this_tick = False
        # Shard shutdown invariant
        if len(shard.processes) < self.min_active_processes:
            shard.empty_ticks += 1
        else:
            shard.empty_ticks = 0
        if shard.empty_ticks >= self.empty_shard_ticks:
            for proc in list(shard.processes.values()):
                self._remove_process(shard, proc)
            self.shards.pop(shard.shard_id, None)

    def render_process_view(self, process_id: str) -> Dict:
        """Render the process-visible snapshot for a given process id."""
        shard = self._get_shard_for_process(process_id)
        if not shard:
            return {}
        proc = shard.processes.get(process_id)
        if not proc:
            return {}
        events = self.process_events.get(process_id, [])
        self.process_events[process_id] = []
        return {
            "tick": shard.tick,
            "grid": render_process_grid(shard, proc),
            "events": [e.__dict__ for e in events],
        }

    def render_spectator_view(self, shard_id: str) -> Dict:
        """Render the spectator snapshot for a given shard."""
        shard = self.shards.get(shard_id)
        if not shard:
            return {}
        return {
            "tick": shard.tick,
            "grid": render_spectator_grid(shard),
            "defragger": shard.defragger.pos,
            "gates": [{"pos": g.pos, "type": g.gate_type.value} for g in shard.gates],
            "processes": [
                {
                    "id": p.process_id,
                    "pos": p.pos,
                }
                for p in shard.processes.values()
            ],
            "watchdog": {
                "quiet_ticks": shard.watchdog.quiet_ticks,
                "countdown": shard.watchdog.countdown,
                "active": shard.watchdog.active,
                "bonus_step": shard.watchdog.bonus_step,
            },
            "say_events": [
                {
                    "sender_id": ev.sender_id,
                    "sender_pos": ev.sender_pos,
                    "message": ev.message,
                    "timestamp_ms": ev.timestamp_ms,
                    "tick": ev.tick,
                    "recipients": [{"id": r.process_id, "pos": r.pos} for r in ev.recipients],
                }
                for ev in shard.say_events
            ],
            "echo_tiles": [{"pos": echo.pos, "tick": echo.tick} for echo in shard.echo_tiles],
        }

    def _trim_old_say_events(self, shard: ShardState) -> None:
        """Retain a short rolling window of SAY events for spectators."""
        max_age = SAY_EVENT_TTL_TICKS - 1
        if not shard.say_events:
            return
        shard.say_events = [ev for ev in shard.say_events if shard.tick - ev.tick <= max_age]

    def _trim_old_echo_tiles(self, shard: ShardState) -> None:
        """Retain a short rolling window of echo tiles for spectators."""
        max_age = ECHO_TTL_TICKS - 1
        if not shard.echo_tiles:
            return
        shard.echo_tiles = [
            echo for echo in shard.echo_tiles if shard.tick - echo.tick <= max_age
        ]

    # Internal helpers

    def _find_or_create_shard(self) -> ShardState:
        for shard in self.shards.values():
            if len(shard.processes) < MAX_PROCESSES_PER_SHARD:
                return shard
        return self.create_shard()

    def _total_processes(self) -> int:
        return sum(len(shard.processes) for shard in self.shards.values())

    def _get_shard_for_process(self, process_id: str) -> Optional[ShardState]:
        shard_id = self.process_to_shard.get(process_id)
        if not shard_id:
            return None
        return self.shards.get(shard_id)

    def _resolve_process_actions(self, shard: ShardState) -> Dict[str, Optional[Tile]]:
        moves: Dict[str, Optional[Tile]] = {}
        for pid, proc in shard.processes.items():
            if not proc.alive:
                moves[pid] = None
                continue
            moves[pid] = self._intent_to_destination(shard, proc)
        # Prevent moving into Defragmenter tile
        for pid, dest in list(moves.items()):
            if dest is not None and dest == shard.defragger.pos:
                moves[pid] = None
        # Resolve same-destination collisions
        dest_map: Dict[Tile, List[str]] = {}
        for pid, dest in moves.items():
            if dest is None:
                continue
            dest_map.setdefault(dest, []).append(pid)
        for dest, pids in dest_map.items():
            if len(pids) > 1:
                for pid in pids:
                    moves[pid] = None
        # Vacated-tile allowance (iterative)
        changed = True
        while changed:
            changed = False
            for pid, dest in list(moves.items()):
                if dest is None:
                    continue
                occupant = self._process_at(shard, dest)
                if occupant and moves.get(occupant.process_id) in (None, occupant.pos):
                    moves[pid] = None
                    changed = True
        return moves

    def _apply_process_moves(self, shard: ShardState, moves: Dict[str, Optional[Tile]]) -> None:
        for pid, dest in moves.items():
            proc = shard.processes.get(pid)
            if not proc or not proc.alive:
                continue
            if dest is None:
                continue
            proc.pos = dest
            # Sprint breaks LOS lock immediately
            if proc.buffered.cmd == CommandType.BUFFER:
                proc.los_lock = False
                proc.last_sprint_tick = shard.tick

    def _intent_to_destination(self, shard: ShardState, proc: ProcessState) -> Optional[Tile]:
        cmd = proc.buffered
        if cmd.cmd in (CommandType.IDLE, CommandType.BROADCAST, CommandType.SAY):
            return None
        if cmd.cmd not in (CommandType.MOVE, CommandType.BUFFER):
            return None
        if cmd.arg is None or not cmd.arg.isdigit():
            return None
        digit = int(cmd.arg)
        if digit not in DIRECTION_MAP:
            return None
        dx, dy = DIRECTION_MAP[digit]
        if dx == 0 and dy == 0:
            return None
        target = (proc.pos[0] + dx, proc.pos[1] + dy)
        if not in_bounds(target):
            return None
        # If tile is not rendered (blocked adjacency), treat as IDLE
        if not self._adjacent_passable(proc.pos, target, shard):
            return None
        if cmd.cmd == CommandType.MOVE:
            return target
        if shard.tick - proc.last_sprint_tick <= SPRINT_COOLDOWN_TICKS:
            return None
        # BUFFER: move up to 3 tiles with randomized turns
        current = proc.pos
        for _ in range(3):
            options = [
                n
                for n in neighbors_8(current)
                if in_bounds(n) and self._adjacent_passable(current, n, shard)
            ]
            if not options:
                break
            # Prefer intended direction if possible
            preferred = (current[0] + dx, current[1] + dy)
            if preferred in options:
                next_tile = preferred
            else:
                next_tile = self.rng.choice(options)
            current = next_tile
        return current

    def _adjacent_passable(self, a: Tile, b: Tile, shard: ShardState) -> bool:
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        if abs(dx) + abs(dy) == 1:
            return not wall_blocks(a, b, shard.walls_set)
        if abs(dx) == 1 and abs(dy) == 1:
            return diagonal_legal(a, b, shard.walls_set)
        return False

    def _resolve_gate_interactions(self, shard: ShardState) -> None:
        gate_positions = {g.pos: g for g in shard.gates}
        for proc in list(shard.processes.values()):
            gate = gate_positions.get(proc.pos)
            if not gate:
                continue
            if gate.gate_type == GateType.STABLE:
                self.persistence.record_survival(proc.call_sign)
                self._remove_process(shard, proc)
            else:
                self.persistence.record_ghost(proc.call_sign)
                self._transfer_process(shard, proc)

    def _resolve_defragger(self, shard: ShardState) -> None:
        target_id, bonus_steps = self._select_defragger_target(shard)
        if target_id:
            shard.defragger.target_id = target_id
        else:
            shard.defragger.target_id = None
        # Determine movement path
        steps = 1 + bonus_steps
        for _ in range(steps):
            next_tile = self._defragger_next_step(shard)
            if next_tile is None:
                break
            shard.defragger.pos = next_tile
            victim = self._process_at(shard, next_tile)
            if victim:
                self._kill_process(shard, victim)
                break

    def _select_defragger_target(self, shard: ShardState) -> Tuple[Optional[str], int]:
        # Broadcast targeting (anti-deadlock)
        target_id = None
        bonus = 0
        if shard.broadcasts:
            latest_ts = max(b.timestamp_ms for b in shard.broadcasts)
            candidates = [b for b in shard.broadcasts if b.timestamp_ms == latest_ts]
            target_id = sorted(candidates, key=lambda b: b.process_id)[0].process_id
            bonus = self._broadcast_bonus(shard, target_id)
            return target_id, bonus
        # LOS targeting (lock persists until sprint)
        locked_targets = [p for p in shard.processes.values() if p.los_lock]
        if locked_targets:
            target = sorted(locked_targets, key=lambda p: p.process_id)[0]
            return target.process_id, 0
        los_targets = [
            p
            for p in shard.processes.values()
            if los_clear(shard.defragger.pos, p.pos, shard.walls_set)
        ]
        if los_targets:
            target = sorted(los_targets, key=lambda p: p.process_id)[0]
            target.los_lock = True
            self._reset_watchdog_on_liveness(shard, reason="los")
            return target.process_id, 0
        # Watchdog bonus
        if shard.watchdog.active:
            bonus = FIBONACCI_ESCALATION[
                min(shard.watchdog.bonus_step, len(FIBONACCI_ESCALATION) - 1)
            ]
        return None, bonus

    def _broadcast_bonus(self, shard: ShardState, target_id: str) -> int:
        count = len([b for b in shard.broadcasts if b.process_id == target_id])
        if count <= 0:
            return 0
        idx = min(count - 1, len(FIBONACCI_ESCALATION) - 1)
        return FIBONACCI_ESCALATION[idx]

    def _defragger_next_step(self, shard: ShardState) -> Optional[Tile]:
        # If no target, patrol randomly
        target_id = shard.defragger.target_id
        if not target_id or target_id not in shard.processes:
            neighbors = adjacent_tiles(shard.defragger.pos, shard.walls_set)
            if not neighbors:
                return None
            return self.rng.choice(neighbors)
        target = shard.processes[target_id]
        # Weighted BFS pathfinding with occasional suboptimal steps
        distances = self._distance_map(shard, target.pos)
        current = shard.defragger.pos
        if current not in distances:
            return None
        neighbors = [n for n in adjacent_tiles(current, shard.walls_set) if n in distances]
        if not neighbors:
            return None
        min_dist = min(distances[n] for n in neighbors)
        if self.rng.random() < DEFRAGGER_WANDER_PROB:
            candidates = [n for n in neighbors if distances[n] <= min_dist + 1]
            weights = [1.0 / (1 + distances[n]) for n in candidates]
            return self._weighted_choice(candidates, weights)
        best = [n for n in neighbors if distances[n] == min_dist]
        return sorted(best)[0]

    def _bfs_path(self, shard: ShardState, start: Tile, goal: Tile) -> List[Tile]:
        queue = deque([start])
        came_from: Dict[Tile, Optional[Tile]] = {start: None}
        while queue:
            cur = queue.popleft()
            if cur == goal:
                break
            for n in adjacent_tiles(cur, shard.walls_set):
                if n not in came_from:
                    came_from[n] = cur
                    queue.append(n)
        if goal not in came_from:
            return [start]
        # Reconstruct path
        path = [goal]
        while path[-1] != start:
            path.append(came_from[path[-1]])
        path.reverse()
        return path

    def _distance_map(self, shard: ShardState, goal: Tile) -> Dict[Tile, int]:
        distances: Dict[Tile, int] = {goal: 0}
        queue = deque([goal])
        while queue:
            cur = queue.popleft()
            for n in adjacent_tiles(cur, shard.walls_set):
                if n not in distances:
                    distances[n] = distances[cur] + 1
                    queue.append(n)
        return distances

    def _weighted_choice(self, candidates: List[Tile], weights: List[float]) -> Tile:
        total = sum(weights)
        if total <= 0:
            return self.rng.choice(candidates)
        r = self.rng.random() * total
        upto = 0.0
        for candidate, weight in zip(candidates, weights):
            upto += weight
            if upto >= r:
                return candidate
        return candidates[-1]

    def _handle_broadcast(self, shard: ShardState, process_id: str, message: str) -> None:
        ts = int(time.time() * 1000)
        shard.broadcasts.append(Broadcast(process_id=process_id, message=message, timestamp_ms=ts))
        event = Event(kind="broadcast", message=f"[BCAST] {message}", timestamp_ms=ts)
        for pid in shard.processes:
            self.process_events.setdefault(pid, []).append(event)
        # Watchdog reset condition: broadcast
        shard.watchdog = self._reset_watchdog_on_liveness(shard, reason="broadcast")

    def _handle_local_chat(self, shard: ShardState, process_id: str, message: str) -> None:
        sender = shard.processes.get(process_id)
        if not sender:
            return
        ts = int(time.time() * 1000)
        recipients = [
            proc
            for pid, proc in shard.processes.items()
            if pid != process_id and proc.alive and _is_adjacent(sender.pos, proc.pos, shard)
        ]
        recipients_by_pid = sorted(recipients, key=lambda proc: proc.process_id)
        recipients_by_spatial = sorted(
            recipients, key=lambda proc: _spatial_order(sender.pos, proc.pos)
        )
        shard.say_events.append(
            SayEvent(
                sender_id=process_id,
                sender_pos=sender.pos,
                message=message,
                recipients=[
                    SayRecipient(process_id=proc.process_id, pos=proc.pos)
                    for proc in recipients_by_spatial
                ],
                timestamp_ms=ts,
                tick=shard.tick,
            )
        )
        if not recipients_by_pid:
            return
        for proc in recipients_by_pid:
            if self.rng.random() < CHAT_ARTIFACT_PROB:
                artifact = self.rng.choice(CHAT_ARTIFACTS)
                self.process_events.setdefault(proc.process_id, []).append(
                    Event(kind="noise", message=artifact, timestamp_ms=ts)
                )
                continue
            text = f"[ADJACENT: {process_id}] {message}"
            self.process_events.setdefault(proc.process_id, []).append(
                Event(kind="local", message=text, timestamp_ms=ts)
            )

    def _kill_process(self, shard: ShardState, proc: ProcessState) -> None:
        proc.alive = False
        self.persistence.record_death(proc.call_sign)
        ts = int(time.time() * 1000)
        event = Event(
            kind="static_burst",
            message="[GLOBAL_ALRT]: ######## STATIC BURST DETECTED ########",
            timestamp_ms=ts,
        )
        for pid in shard.processes:
            self.process_events.setdefault(pid, []).append(event)
        # Watchdog reset condition: kill
        shard.watchdog = self._reset_watchdog_on_liveness(shard, reason="kill")
        self._remove_process(shard, proc)

    def _remove_process(
        self, shard: ShardState, proc: ProcessState, preserve_tokens: bool = False
    ) -> None:
        shard.processes.pop(proc.process_id, None)
        self.process_to_shard.pop(proc.process_id, None)
        self.process_events.pop(proc.process_id, None)
        if not preserve_tokens:
            for token, pid in list(self.session_tokens.items()):
                if pid[0] == proc.process_id:
                    self.session_tokens.pop(token, None)
        self._record_echo(shard, proc.pos)

    def _transfer_process(self, shard: ShardState, proc: ProcessState) -> None:
        # Create new process in a new shard
        old_id = proc.process_id
        self._remove_process(shard, proc, preserve_tokens=True)
        new_shard = self._find_or_create_shard()
        new_proc = ProcessState(
            process_id=str(uuid.uuid4()),
            call_sign=proc.call_sign,
            pos=self._random_empty_tile(
                {p.pos for p in new_shard.processes.values()},
                {g.pos for g in new_shard.gates} | {new_shard.defragger.pos},
            ),
        )
        new_shard.processes[new_proc.process_id] = new_proc
        self.process_to_shard[new_proc.process_id] = new_shard.shard_id
        self.process_events[new_proc.process_id] = []
        for token, (pid, issued_at) in list(self.session_tokens.items()):
            if pid == old_id:
                self.session_tokens[token] = (new_proc.process_id, issued_at)

    def _process_at(self, shard: ShardState, tile: Tile) -> Optional[ProcessState]:
        for proc in shard.processes.values():
            if proc.pos == tile and proc.alive:
                return proc
        return None

    def _random_call_sign(self) -> str:
        """Generate a short call sign for leaderboard identity."""
        adjectives = ["Static", "Ghost", "Null", "Cache", "Wired"]
        nouns = ["Runner", "Process", "Echo", "Trace", "Fork"]
        return f"{self.rng.choice(adjectives)}-{self.rng.choice(nouns)}"

    def _random_empty_tile(
        self,
        occupied: set[Tile],
        forbidden: set[Tile],
        max_attempts: int = 100,
    ) -> Tile:
        attempts = 0
        while attempts < max_attempts:
            tile = (self.rng.randint(0, GRID_SIZE - 1), self.rng.randint(0, GRID_SIZE - 1))
            if tile not in occupied and tile not in forbidden:
                return tile
            attempts += 1
        raise RuntimeError("No empty tile found after max attempts")

    def _generate_walls(self) -> Dict[int, WallEdge]:
        """Generate a wall set that preserves connectivity and avoids dead cells."""
        edges = edge_slots()
        for _ in range(500):
            self.rng.shuffle(edges)
            selected = edges[:80]
            walls_set = set(selected)
            # Ensure connectivity and no 0-exit cells
            if self._walls_valid(walls_set):
                return {i: e for i, e in enumerate(selected)}
        # Fallback (should be rare)
        return {i: e for i, e in enumerate(edges[:80])}

    def _generate_gates(self, walls: Dict[int, WallEdge]) -> List[Gate]:
        """Generate a stable gate and a random number of ghost gates."""
        gates: List[Gate] = []
        stable = Gate(gate_type=GateType.STABLE, pos=self._random_empty_tile(set(), set()))
        gates.append(stable)
        ghost_count = self.rng.randint(1, 3)
        for _ in range(ghost_count):
            pos = self._random_empty_tile(set(), {g.pos for g in gates})
            gates.append(Gate(gate_type=GateType.GHOST, pos=pos))
        return gates

    def _walls_valid(self, walls_set: set[WallEdge]) -> bool:
        from segfault.engine.geometry import exit_count, is_fully_connected

        if not is_fully_connected(walls_set):
            return False
        for x in range(GRID_SIZE):
            for y in range(GRID_SIZE):
                if exit_count((x, y), walls_set) == 0:
                    return False
        return True

    def _reset_watchdog_on_liveness(self, shard: ShardState, reason: str) -> WatchdogState:
        if reason in {"broadcast", "kill", "adjacent", "los"}:
            if (
                shard.watchdog.quiet_ticks >= 6
                or shard.watchdog.countdown > 0
                or shard.watchdog.active
            ):
                self._emit_global_event(shard, "[OK]: LIVENESS RESTORED.")
            shard.watchdog = WatchdogState()
            shard.watchdog.restored_this_tick = True
        return shard.watchdog

    def _emit_global_event(self, shard: ShardState, message: str) -> None:
        ts = int(time.time() * 1000)
        event = Event(kind="system", message=message, timestamp_ms=ts)
        for pid in shard.processes:
            self.process_events.setdefault(pid, []).append(event)

    def _record_echo(self, shard: ShardState, pos: Tile) -> None:
        shard.echo_tiles.append(EchoTile(pos=pos, tick=shard.tick))
        self._emit_global_event(shard, "[WARN]: SECTOR CORRUPTED.")

    def _advance_watchdog(self, shard: ShardState) -> None:
        wd = shard.watchdog
        if wd.restored_this_tick:
            return
        if wd.active:
            wd.bonus_step = min(wd.bonus_step + 1, len(FIBONACCI_ESCALATION) - 1)
            return
        wd.quiet_ticks += 1
        if wd.quiet_ticks == QUIET_TICKS_WARNING:
            wd.countdown = WATCHDOG_COUNTDOWN
            self._emit_global_event(shard, "[WARN]: SCHEDULER LIVENESS DEGRADED.")
            self._emit_global_event(
                shard,
                f"[WARN]: DEADLOCK MITIGATION IN: {wd.countdown:02d} TICKS",
            )
        elif wd.countdown > 0:
            wd.countdown -= 1
            self._emit_global_event(
                shard,
                f"[WARN]: DEADLOCK MITIGATION IN: {wd.countdown:02d} TICKS",
            )
            if wd.countdown == 0:
                wd.active = True
                wd.bonus_step = 0
                self._emit_global_event(shard, "[CRITICAL]: WATCHDOG TRIGGERED.")
                self._emit_global_event(shard, "[CRITICAL]: EXECUTION REBALANCE APPLIED.")


def render_process_grid(shard: ShardState, proc: ProcessState) -> str:
    """Return ASCII grid for the process UI."""
    # Build visibility set for adjacent cluster
    cluster = _adjacent_cluster(shard, proc.process_id)
    visible_tiles = set()
    for pid in cluster:
        p = shard.processes[pid]
        visible_tiles.add(p.pos)
        for tile in adjacent_tiles(p.pos, shard.walls_set):
            visible_tiles.add(tile)
    # Bounding box
    min_x = min(t[0] for t in visible_tiles)
    max_x = max(t[0] for t in visible_tiles)
    min_y = min(t[1] for t in visible_tiles)
    max_y = max(t[1] for t in visible_tiles)

    rows: List[str] = []
    for y in range(min_y, max_y + 1):
        row_parts: List[str] = []
        for x in range(min_x, max_x + 1):
            tile = (x, y)
            if tile not in visible_tiles:
                row_parts.append("".ljust(10))
                continue
            label = _tile_label(shard, proc, tile)
            digit = _digit_for_tile(proc.pos, tile)
            if digit is None:
                digit = " "
            row_parts.append(f"[{digit} {label:<5}] ")
        rows.append("".join(row_parts).rstrip())
    return "\n".join(rows)


def _digit_for_tile(center: Tile, tile: Tile) -> Optional[str]:
    dx = tile[0] - center[0]
    dy = tile[1] - center[1]
    if abs(dx) > 1 or abs(dy) > 1:
        return None
    # Map dx,dy to keypad digit
    mapping = {
        (-1, -1): "1",
        (0, -1): "2",
        (1, -1): "3",
        (-1, 0): "4",
        (0, 0): "5",
        (1, 0): "6",
        (-1, 1): "7",
        (0, 1): "8",
        (1, 1): "9",
    }
    return mapping.get((dx, dy))


def _tile_label(shard: ShardState, proc: ProcessState, tile: Tile) -> str:
    if tile == proc.pos:
        return "SELF"
    if shard.defragger.pos == tile:
        return "DEFRG"
    if tile in {p.pos for p in shard.processes.values() if p.process_id != proc.process_id}:
        return "PROC"
    if tile in {g.pos for g in shard.gates}:
        return "GATE"
    return ""


def render_spectator_grid(shard: ShardState) -> List[List[str]]:
    grid = [["." for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
    for wall in shard.walls.values():
        # Mark walls minimally; UI can render edges differently
        (x1, y1), (x2, y2) = wall.segment()
        wx, wy = int(x1), int(y1)
        if 0 <= wx < GRID_SIZE and 0 <= wy < GRID_SIZE:
            grid[wy][wx] = "#"
    for gate in shard.gates:
        x, y = gate.pos
        grid[y][x] = "S" if gate.gate_type == GateType.STABLE else "G"
    for proc in shard.processes.values():
        x, y = proc.pos
        grid[y][x] = "P"
    dx, dy = shard.defragger.pos
    grid[dy][dx] = "D"
    for echo in shard.echo_tiles:
        ex, ey = echo.pos
        if 0 <= ex < GRID_SIZE and 0 <= ey < GRID_SIZE and grid[ey][ex] == ".":
            grid[ey][ex] = "E"
    return grid


def _adjacent_cluster(shard: ShardState, process_id: str) -> List[str]:
    start = shard.processes[process_id]
    cluster = set([process_id])
    changed = True
    while changed:
        changed = False
        for pid, proc in shard.processes.items():
            if pid in cluster:
                continue
            if any(_is_adjacent(proc.pos, shard.processes[c].pos, shard) for c in cluster):
                cluster.add(pid)
                changed = True
    return list(cluster)


def _is_adjacent(a: Tile, b: Tile, shard: ShardState) -> bool:
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    if dx > 1 or dy > 1:
        return False
    if dx == 0 and dy == 0:
        return False
    if dx + dy == 1:
        return not wall_blocks(a, b, shard.walls_set)
    return diagonal_legal(a, b, shard.walls_set)


def _spatial_order(a: Tile, b: Tile) -> int:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    order = {
        (-1, -1): 1,
        (0, -1): 2,
        (1, -1): 3,
        (-1, 0): 4,
        (1, 0): 6,
        (-1, 1): 7,
        (0, 1): 8,
        (1, 1): 9,
    }
    return order.get((dx, dy), 99)
