from segfault.common.types import Command, CommandType, GateType
from segfault.engine.engine import TickEngine
from segfault.engine.state import DefragmenterState, Gate, ProcessState, ShardState
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


def _make_engine():
    return TickEngine(DummyPersist(), seed=1)


def test_collision_same_destination():
    engine = _make_engine()
    shard = engine.create_shard()
    shard.walls = {}
    shard.processes = {}
    shard.defragger = DefragmenterState(pos=(10, 10))
    p1 = ProcessState(process_id="p1", call_sign="A", pos=(1, 1))
    p2 = ProcessState(process_id="p2", call_sign="B", pos=(1, 3))
    # Both target (1,2)
    p1.buffered = Command(CommandType.MOVE, "8")  # move south to (1,2)
    p2.buffered = Command(CommandType.MOVE, "2")  # move north to (1,2)
    shard.processes = {p1.process_id: p1, p2.process_id: p2}
    moves = engine._resolve_process_actions(shard)
    assert moves["p1"] is None
    assert moves["p2"] is None


def test_swap_allowed_when_vacated():
    engine = _make_engine()
    shard = engine.create_shard()
    shard.walls = {}
    shard.processes = {}
    shard.defragger = DefragmenterState(pos=(10, 10))
    p1 = ProcessState(process_id="p1", call_sign="A", pos=(1, 1))
    p2 = ProcessState(process_id="p2", call_sign="B", pos=(2, 1))
    p1.buffered = Command(CommandType.MOVE, "6")  # move east to (2,1)
    p2.buffered = Command(CommandType.MOVE, "4")  # move west to (1,1)
    shard.processes = {p1.process_id: p1, p2.process_id: p2}
    moves = engine._resolve_process_actions(shard)
    # Both moving into each other's tile (swap) allowed
    assert moves["p1"] == (2, 1)
    assert moves["p2"] == (1, 1)


def test_occupied_tile_idles_if_occupant_idles():
    engine = _make_engine()
    shard = engine.create_shard()
    shard.walls = {}
    shard.processes = {}
    shard.defragger = DefragmenterState(pos=(10, 10))
    p1 = ProcessState(process_id="p1", call_sign="A", pos=(1, 1))
    p2 = ProcessState(process_id="p2", call_sign="B", pos=(1, 2))
    p1.buffered = Command(CommandType.MOVE, "8")  # move south to (1,2)
    p2.buffered = Command(CommandType.IDLE, None)
    shard.processes = {p1.process_id: p1, p2.process_id: p2}
    moves = engine._resolve_process_actions(shard)
    assert moves["p1"] is None
