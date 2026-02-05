from segfault.engine.geometry import (
    WallEdge,
    diagonal_legal,
    segment_intersection_blocks,
    tile_center,
)


def test_vertex_touch_allows_diagonal():
    # Diagonal from (0,0) to (1,1) touches wall endpoint at (1,1)
    walls = {WallEdge((0, 1), (1, 1)).canonical()}
    assert diagonal_legal((0, 0), (1, 1), walls) is True


def test_proper_crossing_blocks():
    # Horizontal LOS crossing a vertical wall edge at midpoint
    seg = (tile_center((0, 0)), tile_center((2, 0)))
    wall = WallEdge((1, 0), (2, 0)).canonical().segment()
    assert segment_intersection_blocks(seg, wall) is True


def test_colinear_overlap_blocks():
    seg = ((0.0, 0.0), (2.0, 0.0))
    wall = ((1.0, 0.0), (3.0, 0.0))
    assert segment_intersection_blocks(seg, wall) is True
