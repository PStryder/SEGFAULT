import tempfile
from pathlib import Path

from segfault.common.types import GateType
from segfault.engine.engine import TickEngine
from segfault.engine.state import Gate, ProcessState
from segfault.persist.sqlite import SqlitePersistence


def _make_engine(db_path: Path, **kwargs) -> TickEngine:
    persistence = SqlitePersistence(str(db_path))
    return TickEngine(persistence, **kwargs)


def test_replay_tick_recorded():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "replay.db"
        engine = _make_engine(db_path, seed=1)
        _, pid = engine.join_process()
        shard_id = engine.process_to_shard[pid]

        engine.tick_once()
        engine.persistence.flush()

        ticks = engine.persistence.get_replay_ticks(shard_id, start_tick=1, limit=1)
        assert len(ticks) == 1
        snapshot = ticks[0]["snapshot"]
        for key in ("shard_id", "tick", "walls", "gates", "processes", "defragger", "watchdog"):
            assert key in snapshot
        engine.persistence.close()


def test_replay_tick_events_tracked():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "replay.db"
        persistence = SqlitePersistence(str(db_path))
        engine = TickEngine(persistence, seed=2)
        shard = engine.create_shard()
        gate_pos = (2, 2)
        shard.gates = [Gate(gate_type=GateType.STABLE, pos=gate_pos)]
        proc = ProcessState(process_id="p1", call_sign="A", pos=gate_pos)
        shard.processes[proc.process_id] = proc
        engine.process_to_shard[proc.process_id] = shard.shard_id

        engine.tick_once()
        persistence.flush()

        ticks = persistence.get_replay_ticks(shard.shard_id, start_tick=1, limit=1)
        snapshot = ticks[0]["snapshot"]
        events = snapshot["events"]
        assert proc.process_id in events["survivals"]
        persistence.close()


def test_replay_shard_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "replay.db"
        persistence = SqlitePersistence(str(db_path))
        engine = TickEngine(persistence, empty_shard_ticks=1, min_active_processes=1)
        shard = engine.create_shard()
        persistence.flush()

        shards = persistence.list_replay_shards()
        shard_row = next(s for s in shards if s["shard_id"] == shard.shard_id)
        assert shard_row["ended_at"] is None

        engine.tick_once()
        persistence.flush()

        shards = persistence.list_replay_shards()
        shard_row = next(s for s in shards if s["shard_id"] == shard.shard_id)
        assert shard_row["ended_at"] is not None
        assert shard_row["total_ticks"] == 1
        persistence.close()


def test_replay_disabled_by_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "replay.db"
        persistence = SqlitePersistence(str(db_path))
        engine = TickEngine(persistence, enable_replay_logging=False)
        engine.create_shard()
        engine.tick_once()
        persistence.flush()

        assert persistence.list_replay_shards() == []
        assert persistence.get_replay_ticks("missing", start_tick=0, limit=10) == []
        persistence.close()


def test_replay_tick_snapshot_format():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "replay.db"
        engine = _make_engine(db_path, seed=3)
        _, pid = engine.join_process()
        shard_id = engine.process_to_shard[pid]
        engine.tick_once()
        engine.persistence.flush()

        ticks = engine.persistence.get_replay_ticks(shard_id, start_tick=1, limit=1)
        snapshot = ticks[0]["snapshot"]
        assert isinstance(snapshot["walls"], list)
        assert all(len(w) == 4 for w in snapshot["walls"])
        assert isinstance(snapshot["processes"], list)
        proc = snapshot["processes"][0]
        for key in (
            "id",
            "call_sign",
            "pos",
            "alive",
            "buffered_cmd",
            "buffered_arg",
            "los_lock",
            "last_sprint_tick",
        ):
            assert key in proc
        defragger = snapshot["defragger"]
        assert defragger["target_reason"] in {"broadcast", "los", "watchdog", "patrol"}
        engine.persistence.close()
