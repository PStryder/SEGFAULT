from segfault.engine import engine as engine_module
from segfault.engine.engine import TickEngine
from segfault.engine.state import DefragmenterState, ProcessState
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

    def record_replay_tick(self, shard_id: str, tick: int, snapshot: dict) -> None:
        pass

    def register_replay_shard(self, shard_id: str) -> None:
        pass

    def finalize_replay_shard(self, shard_id: str, total_ticks: int, stats: dict) -> None:
        pass

    def list_replay_shards(self, limit: int = 50):
        return []

    def get_replay_ticks(self, shard_id: str, start_tick: int = 0, limit: int = 100):
        return []


def test_visibility_radius_scales_with_cluster():
    engine = TickEngine(DummyPersist(), seed=1)
    shard = engine.create_shard()
    shard.walls = {}
    shard.processes = {}
    shard.defragger = DefragmenterState(pos=(0, 0))

    p1 = ProcessState(process_id="p1", call_sign="A", pos=(5, 5))
    shard.processes[p1.process_id] = p1

    cluster = engine_module._adjacent_cluster(shard, p1.process_id)
    visible = engine_module._visible_tiles_for_cluster(shard, cluster)
    assert (6, 5) in visible
    assert (7, 5) not in visible

    p2 = ProcessState(process_id="p2", call_sign="B", pos=(6, 5))
    shard.processes[p2.process_id] = p2
    cluster = engine_module._adjacent_cluster(shard, p1.process_id)
    visible = engine_module._visible_tiles_for_cluster(shard, cluster)
    assert (8, 5) in visible
    assert (9, 5) not in visible

    p3 = ProcessState(process_id="p3", call_sign="C", pos=(7, 5))
    shard.processes[p3.process_id] = p3
    cluster = engine_module._adjacent_cluster(shard, p1.process_id)
    visible = engine_module._visible_tiles_for_cluster(shard, cluster)
    assert (10, 5) in visible
    assert (11, 5) not in visible

    p4 = ProcessState(process_id="p4", call_sign="D", pos=(8, 5))
    shard.processes[p4.process_id] = p4
    cluster = engine_module._adjacent_cluster(shard, p1.process_id)
    visible = engine_module._visible_tiles_for_cluster(shard, cluster)
    assert (12, 5) in visible
