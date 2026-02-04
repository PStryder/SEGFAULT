from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from segfault.common.constants import GRID_SIZE
from segfault.common.types import GateType, Tile
from segfault.engine.geometry import (
    adjacent_edge_slots,
    adjacent_tiles,
    exit_count,
    in_bounds,
    is_fully_connected,
    neighbors_8,
    orthogonal_neighbors,
    WallEdge,
)
from segfault.engine.state import Gate, ShardState


def drift_walls(shard: ShardState, rng: random.Random) -> None:
    """Move a subset of walls by one edge slot while preserving constraints."""
    wall_ids = list(shard.walls.keys())
    if not wall_ids:
        return
    min_count = max(1, int(len(wall_ids) * 0.10))
    max_count = max(1, int(len(wall_ids) * 0.25))
    move_count = rng.randint(min_count, max_count)
    rng.shuffle(wall_ids)
    selected = sorted(wall_ids[:move_count])

    desired: Dict[int, Optional[WallEdge]] = {}
    for wall_id in selected:
        current = shard.walls[wall_id]
        candidates = adjacent_edge_slots(current)
        rng.shuffle(candidates)
        desired_edge = candidates[0] if candidates else None
        desired[wall_id] = desired_edge

    for wall_id in selected:
        target = desired.get(wall_id)
        if target is None:
            continue
        current = shard.walls[wall_id]
        # If target already occupied by a wall, skip (deterministic: lower ID wins)
        if target in shard.walls_set:
            continue
        # Tentatively move and validate constraints
        shard.walls[wall_id] = target
        if not _drift_constraints_ok(shard):
            shard.walls[wall_id] = current


def drift_gates(shard: ShardState, rng: random.Random) -> None:
    """Move gates by one tile, respecting occupancy constraints."""
    occupied = {p.pos for p in shard.processes.values()} | {shard.defragger.pos}
    for gate in shard.gates:
        occupied_with_gates = occupied | {g.pos for g in shard.gates if g is not gate}
        candidates = [t for t in orthogonal_neighbors(gate.pos) if in_bounds(t)]
        rng.shuffle(candidates)
        moved = False
        for tile in candidates:
            if tile in occupied_with_gates:
                continue
            gate.pos = tile
            moved = True
            break
        if not moved:
            gate.pos = gate.pos


def _drift_constraints_ok(shard: ShardState) -> bool:
    walls = shard.walls_set
    if not is_fully_connected(walls):
        return False
    # No 0-exit cells
    for x in range(GRID_SIZE):
        for y in range(GRID_SIZE):
            if exit_count((x, y), walls) == 0:
                return False
    # Stable port cannot be sealed off (must have at least one exit)
    stable = next((g for g in shard.gates if g.gate_type == GateType.STABLE), None)
    if stable and exit_count(stable.pos, walls) == 0:
        return False
    return True
