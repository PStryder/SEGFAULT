from segfault.engine.drift import drift_walls
from segfault.engine.engine import TickEngine
from segfault.engine.geometry import exit_count, is_fully_connected
from segfault.persist.base import Persistence


class DummyPersist(Persistence):
    def record_survival(self, call_sign: str) -> None:
        pass

    def record_death(self, call_sign: str) -> None:
        pass

    def record_ghost(self, call_sign: str) -> None:
        pass

    def leaderboard(self):
        return []


def test_drift_preserves_wall_count_and_connectivity():
    engine = TickEngine(DummyPersist(), seed=123)
    shard = engine.create_shard()
    before_count = len(shard.walls)
    drift_walls(shard, engine.rng)
    after_count = len(shard.walls)
    assert before_count == after_count
    assert is_fully_connected(shard.walls_set)
    for x in range(20):
        for y in range(20):
            assert exit_count((x, y), shard.walls_set) > 0
