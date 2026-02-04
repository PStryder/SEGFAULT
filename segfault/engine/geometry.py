from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, List, Set, Tuple

from segfault.common.constants import GRID_SIZE
from segfault.common.types import Edge, Point, Tile

EPS = 1e-9


@dataclass(frozen=True)
class WallEdge:
    """Wall edge represented by the two orthogonal tiles it separates.

    The tiles must be orthogonal neighbors (Manhattan distance == 1).
    """

    a: Tile
    b: Tile

    def canonical(self) -> "WallEdge":
        return WallEdge(*sorted([self.a, self.b]))  # type: ignore[arg-type]

    def segment(self) -> Edge:
        return edge_segment_for_tiles(self.a, self.b)


def in_bounds(tile: Tile) -> bool:
    x, y = tile
    return 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE


def tile_center(tile: Tile) -> Point:
    x, y = tile
    return (x + 0.5, y + 0.5)


def orthogonal_neighbors(tile: Tile) -> List[Tile]:
    x, y = tile
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def neighbors_8(tile: Tile) -> List[Tile]:
    x, y = tile
    return [
        (x + 1, y),
        (x - 1, y),
        (x, y + 1),
        (x, y - 1),
        (x + 1, y + 1),
        (x + 1, y - 1),
        (x - 1, y + 1),
        (x - 1, y - 1),
    ]


def edge_segment_for_tiles(a: Tile, b: Tile) -> Edge:
    """Return the wall edge segment separating two orthogonal neighboring tiles."""
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    if abs(dx) + abs(dy) != 1:
        raise ValueError("Wall edge requires orthogonal adjacent tiles")
    # Tiles are unit squares from (x,y) to (x+1,y+1). Edge lies on boundary.
    if dx == 1:  # b is east of a; vertical edge at x+1
        x = ax + 1
        return ((x, ay), (x, ay + 1))
    if dx == -1:  # b is west
        x = ax
        return ((x, ay), (x, ay + 1))
    if dy == 1:  # b is north; horizontal edge at y+1
        y = ay + 1
        return ((ax, y), (ax + 1, y))
    # dy == -1
    y = ay
    return ((ax, y), (ax + 1, y))


def wall_blocks(a: Tile, b: Tile, walls: Set[WallEdge]) -> bool:
    if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
        return False
    edge = WallEdge(a, b).canonical()
    return edge in walls


def segment_intersection_blocks(seg: Edge, wall_edge: Edge) -> bool:
    """Return True if the segment should be blocked by the wall edge.

    Rules:
    - Proper crossings block.
    - Colinear overlap blocks.
    - Touching at endpoints does NOT block.
    """

    p1, p2 = seg
    q1, q2 = wall_edge

    o1 = orientation(p1, p2, q1)
    o2 = orientation(p1, p2, q2)
    o3 = orientation(q1, q2, p1)
    o4 = orientation(q1, q2, p2)

    # Colinear - check overlap length > 0
    if o1 == 0 and o2 == 0 and o3 == 0 and o4 == 0:
        return colinear_overlap(p1, p2, q1, q2)

    # Proper crossing blocks
    if o1 != 0 and o2 != 0 and o3 != 0 and o4 != 0 and o1 != o2 and o3 != o4:
        return True

    # Touching at a wall endpoint does not block
    if on_segment(p1, p2, q1) or on_segment(p1, p2, q2):
        return False

    return False


def colinear_overlap(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    """Return True if two colinear segments overlap with non-zero length."""
    if not (min(p1[0], p2[0]) - EPS <= max(q1[0], q2[0]) and max(p1[0], p2[0]) + EPS >= min(q1[0], q2[0])):
        return False
    if not (min(p1[1], p2[1]) - EPS <= max(q1[1], q2[1]) and max(p1[1], p2[1]) + EPS >= min(q1[1], q2[1])):
        return False
    # Compute overlap length on dominant axis
    if abs(p1[0] - p2[0]) >= abs(p1[1] - p2[1]):
        left = max(min(p1[0], p2[0]), min(q1[0], q2[0]))
        right = min(max(p1[0], p2[0]), max(q1[0], q2[0]))
    else:
        left = max(min(p1[1], p2[1]), min(q1[1], q2[1]))
        right = min(max(p1[1], p2[1]), max(q1[1], q2[1]))
    return right - left > EPS


def orientation(a: Point, b: Point, c: Point) -> int:
    """Return orientation of (a,b,c): 0 colinear, 1 clockwise, 2 counterclockwise."""
    val = (b[1] - a[1]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[1] - a[1])
    if abs(val) < EPS:
        return 0
    return 1 if val > 0 else 2


def on_segment(a: Point, b: Point, c: Point) -> bool:
    """Return True if point c lies on segment ab (inclusive)."""
    if min(a[0], b[0]) - EPS <= c[0] <= max(a[0], b[0]) + EPS and min(a[1], b[1]) - EPS <= c[1] <= max(a[1], b[1]) + EPS:
        # Colinear check
        return orientation(a, b, c) == 0
    return False


def diagonal_legal(a: Tile, b: Tile, walls: Set[WallEdge]) -> bool:
    """Diagonal move/LOS is legal if center-to-center segment does not intersect a wall edge."""
    seg = (tile_center(a), tile_center(b))
    for wall in walls:
        if segment_intersection_blocks(seg, wall.segment()):
            return False
    return True


def adjacent_tiles(tile: Tile, walls: Set[WallEdge]) -> List[Tile]:
    """Return passable neighbors (orthogonal and diagonal) based on wall geometry."""
    neighbors: List[Tile] = []
    for n in neighbors_8(tile):
        if not in_bounds(n):
            continue
        dx = n[0] - tile[0]
        dy = n[1] - tile[1]
        if abs(dx) + abs(dy) == 1:
            if not wall_blocks(tile, n, walls):
                neighbors.append(n)
        elif abs(dx) == 1 and abs(dy) == 1:
            if diagonal_legal(tile, n, walls):
                neighbors.append(n)
    return neighbors


def los_clear(a: Tile, b: Tile, walls: Set[WallEdge]) -> bool:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    if dx == 0 or dy == 0 or abs(dx) == abs(dy):
        seg = (tile_center(a), tile_center(b))
        for wall in walls:
            if segment_intersection_blocks(seg, wall.segment()):
                return False
        return True
    return False


def all_tiles() -> List[Tile]:
    return [(x, y) for x in range(GRID_SIZE) for y in range(GRID_SIZE)]


def reachable_component(start: Tile, walls: Set[WallEdge]) -> Set[Tile]:
    visited: Set[Tile] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in visited:
            continue
        visited.add(cur)
        for n in adjacent_tiles(cur, walls):
            if n not in visited:
                stack.append(n)
    return visited


def is_fully_connected(walls: Set[WallEdge]) -> bool:
    tiles = all_tiles()
    if not tiles:
        return True
    comp = reachable_component(tiles[0], walls)
    return len(comp) == len(tiles)


def exit_count(tile: Tile, walls: Set[WallEdge]) -> int:
    return len(adjacent_tiles(tile, walls))


def edge_slots() -> List[WallEdge]:
    """All possible interior wall edges between tiles."""
    edges: List[WallEdge] = []
    for x in range(GRID_SIZE):
        for y in range(GRID_SIZE):
            if x + 1 < GRID_SIZE:
                edges.append(WallEdge((x, y), (x + 1, y)).canonical())
            if y + 1 < GRID_SIZE:
                edges.append(WallEdge((x, y), (x, y + 1)).canonical())
    # remove duplicates
    return list({e for e in edges})


def adjacent_edge_slots(edge: WallEdge) -> List[WallEdge]:
    """Return adjacent edge slots sharing a vertex with the given edge."""
    (x1, y1), (x2, y2) = edge.segment()
    vertices = {(x1, y1), (x2, y2)}
    candidates: Set[WallEdge] = set()
    for candidate in edge_slots():
        if candidate == edge.canonical():
            continue
        c1, c2 = candidate.segment()
        if c1 in vertices or c2 in vertices:
            candidates.add(candidate)
    return list(candidates)
