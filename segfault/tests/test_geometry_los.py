from segfault.engine.geometry import WallEdge, los_clear


def wall(a, b):
    return WallEdge(a, b).canonical()


def test_los_blocked_by_orthogonal_wall():
    walls = {wall((2, 2), (2, 3))}
    assert los_clear((2, 1), (2, 4), walls) is False


def test_los_diagonal_blocked_by_corner():
    walls = {wall((1, 1), (2, 1)), wall((1, 1), (1, 2))}
    assert los_clear((1, 1), (2, 2), walls) is False


def test_los_regression_diagonal_wall_between():
    walls = {wall((1, 1), (2, 1)), wall((1, 1), (1, 2))}
    assert los_clear((0, 0), (2, 2), walls) is False
