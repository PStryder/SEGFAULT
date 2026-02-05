from segfault.common.types import Broadcast
from segfault.engine.engine import TickEngine
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


def test_broadcast_targeting_and_escalation():
    engine = TickEngine(DummyPersist(), seed=1)
    shard = engine.create_shard()
    shard.broadcasts = [
        Broadcast(process_id="b", message="1", timestamp_ms=100),
        Broadcast(process_id="a", message="2", timestamp_ms=100),
    ]
    target_id, bonus = engine._select_defragger_target(shard)
    assert target_id == "a"  # lowest id wins tie
    assert bonus == 1


def test_broadcast_escalation_resets_per_tick():
    engine = TickEngine(DummyPersist(), seed=1)
    shard = engine.create_shard()
    shard.broadcasts = [
        Broadcast(process_id="a", message="1", timestamp_ms=100),
        Broadcast(process_id="a", message="2", timestamp_ms=101),
    ]
    target_id, bonus = engine._select_defragger_target(shard)
    assert target_id == "a"
    assert bonus == 3
    shard.broadcasts.clear()
    target_id, bonus = engine._select_defragger_target(shard)
    assert target_id is None
    assert bonus == 0
