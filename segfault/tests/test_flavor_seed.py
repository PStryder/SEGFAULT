import gc
import tempfile
import time
from pathlib import Path

from segfault.persist.sqlite import SqlitePersistence


def test_flavor_seed_and_random_selection():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        md_path = Path(tmpdir) / "flavor.md"
        md_path.write_text(
            "\n".join(
                [
                    "# Flavor",
                    "",
                    "- [PROC] kernel whispers in the buffer",
                    "- [SPEC] watcher blinks behind glass",
                    "- [SYS] syslog hums in the dark",
                    "- orphaned record drifts",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        persistence = SqlitePersistence(str(db_path))
        assert persistence.flavor_count() == 0

        inserted = persistence.seed_flavor_from_markdown(str(md_path))
        assert inserted == 4
        assert persistence.flavor_count() == 4

        assert persistence.random_flavor("proc") is not None
        assert persistence.random_flavor("spec") is not None
        assert persistence.random_flavor("sys") is not None
        assert persistence.random_flavor() is not None

        entry = persistence.random_flavor()
        assert entry is not None
        assert entry["text"]
        assert entry["channel"] in {"proc", "spec", "sys"}

        persistence.close()
        persistence = None
        gc.collect()
        time.sleep(0.05)
