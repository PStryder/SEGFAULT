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


def _make_shard() -> ShardState:
    return ShardState(
        shard_id="shard",
        walls={},
        gates=[],
        processes={},
        defragger=DefragmenterState(pos=(0, 0)),
    )


def test_ghost_gate_remaps_token():
    engine = TickEngine(DummyPersist(), seed=1)
    shard = _make_shard()
    gate_pos = (5, 5)
    shard.gates = [Gate(gate_type=GateType.GHOST, pos=gate_pos)]

    proc = ProcessState(process_id="old", call_sign="A", pos=gate_pos)
    shard.processes[proc.process_id] = proc
    engine.shards[shard.shard_id] = shard
    engine.process_to_shard[proc.process_id] = shard.shard_id
    engine.process_events[proc.process_id] = []
    engine.session_tokens["token"] = (proc.process_id, 123)

    engine._resolve_gate_interactions(shard)

    new_pid = engine.session_tokens["token"][0]
    assert new_pid != proc.process_id
    assert new_pid in engine.process_to_shard
    assert proc.process_id not in shard.processes


def test_sprint_cooldown_blocks_back_to_back():
    engine = TickEngine(DummyPersist(), seed=1)
    shard = _make_shard()
    proc = ProcessState(process_id="p", call_sign="A", pos=(5, 5))
    shard.processes[proc.process_id] = proc
    engine.shards[shard.shard_id] = shard
    engine.process_to_shard[proc.process_id] = shard.shard_id

    shard.tick = 5
    proc.last_sprint_tick = 5
    proc.buffered = Command(CommandType.BUFFER, "6")

    dest = engine._intent_to_destination(shard, proc)
    assert dest is None


def test_echo_tile_created_on_remove():
    engine = TickEngine(DummyPersist(), seed=1)
    shard = _make_shard()
    proc = ProcessState(process_id="p", call_sign="A", pos=(4, 4))
    other = ProcessState(process_id="q", call_sign="B", pos=(6, 6))
    shard.processes = {proc.process_id: proc, other.process_id: other}
    engine.shards[shard.shard_id] = shard
    engine.process_to_shard[proc.process_id] = shard.shard_id
    engine.process_to_shard[other.process_id] = shard.shard_id

    engine._remove_process(shard, proc)

    assert shard.echo_tiles
    assert shard.echo_tiles[-1].pos == (4, 4)
