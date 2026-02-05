import random

from segfault.engine.engine import CHAT_ARTIFACTS, TickEngine
from segfault.engine.state import DefragmenterState, ProcessState, ShardState
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


def _make_shard() -> ShardState:
    return ShardState(
        shard_id="shard",
        walls={},
        gates=[],
        processes={},
        defragger=DefragmenterState(pos=(0, 0)),
    )


def test_say_adjacent_delivery_and_order(monkeypatch):
    from segfault.engine import engine as engine_module

    monkeypatch.setattr(engine_module, "CHAT_ARTIFACT_PROB", 0.0)

    engine = TickEngine(DummyPersist(), seed=1)
    shard = _make_shard()
    engine.shards[shard.shard_id] = shard

    sender = ProcessState(process_id="a", call_sign="A", pos=(5, 5))
    right = ProcessState(process_id="b", call_sign="B", pos=(6, 5))
    diag = ProcessState(process_id="c", call_sign="C", pos=(4, 4))
    far = ProcessState(process_id="d", call_sign="D", pos=(8, 8))

    shard.processes = {
        sender.process_id: sender,
        right.process_id: right,
        diag.process_id: diag,
        far.process_id: far,
    }

    engine._handle_local_chat(shard, sender.process_id, "hello")

    assert sender.process_id not in engine.process_events
    assert right.process_id in engine.process_events
    assert diag.process_id in engine.process_events
    assert far.process_id not in engine.process_events

    right_event = engine.process_events[right.process_id][0]
    diag_event = engine.process_events[diag.process_id][0]
    assert right_event.message == f"[ADJACENT: {sender.process_id}] hello"
    assert diag_event.message == f"[ADJACENT: {sender.process_id}] hello"

    say_event = shard.say_events[0]
    recipient_ids = [r.process_id for r in say_event.recipients]
    assert recipient_ids == ["c", "b"]


def test_say_noise_artifact(monkeypatch):
    from segfault.engine import engine as engine_module

    monkeypatch.setattr(engine_module, "CHAT_ARTIFACT_PROB", 1.0)

    engine = TickEngine(DummyPersist(), seed=1)
    engine.rng = random.Random(0)
    shard = _make_shard()
    engine.shards[shard.shard_id] = shard

    sender = ProcessState(process_id="a", call_sign="A", pos=(5, 5))
    right = ProcessState(process_id="b", call_sign="B", pos=(6, 5))
    shard.processes = {
        sender.process_id: sender,
        right.process_id: right,
    }

    engine._handle_local_chat(shard, sender.process_id, "hello")

    event = engine.process_events[right.process_id][0]
    assert event.kind == "noise"
    assert event.message in CHAT_ARTIFACTS
