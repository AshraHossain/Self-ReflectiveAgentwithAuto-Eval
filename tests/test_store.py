"""TRACE-03: the run-history contract.

Every test uses a real file under ``tmp_path``. An in-memory database is wrong here: under
connection-per-call each connection to one is a fresh empty database, so the second call
reports that the table does not exist (02-RESEARCH.md Pitfall 4).
"""

from __future__ import annotations

import sqlite3
import stat
import threading
import uuid
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from eacp.store import (
    MAX_LIST_LIMIT,
    RunRecord,
    RunStore,
    SQLiteRunStore,
    StepRecord,
    utc_now,
)

T0 = "2026-09-27T12:00:00.000000+00:00"


def _run(workflow_id: str = "contract_review", started_at: str = T0) -> RunRecord:
    return RunRecord(
        run_id=uuid.uuid4().hex,
        workflow_id=workflow_id,
        backend_type="langgraph",
        policy_id="demo",
        policy_hash="a" * 64,
        status="running",
        started_at=started_at,
        ended_at=None,
        metrics={},
    )


def _step(store: RunStore, run_id: str, seq: int) -> None:
    store.append_step(
        run_id,
        seq=seq,
        name=f"node_{seq}",
        started_at=f"2026-09-27T12:00:0{seq}.000000+00:00",
        ended_at=f"2026-09-27T12:00:0{seq}.500000+00:00",
        outcome="ok",
        attributes={"gen_ai.usage.input_tokens": 100 * seq},
    )


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return SQLiteRunStore(tmp_path / "runs.db")


def test_sqlite_store_satisfies_protocol(tmp_path: Path) -> None:
    # The annotation is the conformance gate (mypy --strict); the assert is pytest's half.
    # A runtime isinstance check is deliberately absent: it is signature-blind (Finding 7).
    store: RunStore = SQLiteRunStore(tmp_path / "runs.db")
    assert store.get_run("nope") is None


def test_utc_now_is_canonical_iso8601() -> None:
    ts = utc_now()
    assert ts.endswith("+00:00"), ts
    assert len(ts) == len(T0), ts  # microsecond precision, fixed width -> sorts lexically


def test_run_roundtrip(store: RunStore) -> None:
    run = _run()
    store.start_run(run)
    for seq in range(3):
        _step(store, run.run_id, seq)
    store.finish_run(
        run.run_id,
        status="succeeded",
        ended_at="2026-09-27T12:00:05.000000+00:00",
        metrics={"tokens": 300, "cost": "0.02"},
    )

    expected = replace(
        run,
        status="succeeded",
        ended_at="2026-09-27T12:00:05.000000+00:00",
        metrics={"tokens": 300, "cost": "0.02"},
    )
    assert store.get_run(run.run_id) == expected

    steps = store.list_steps(run.run_id)
    assert [s.seq for s in steps] == [0, 1, 2]
    assert steps[2] == StepRecord(
        run_id=run.run_id,
        seq=2,
        name="node_2",
        started_at="2026-09-27T12:00:02.000000+00:00",
        ended_at="2026-09-27T12:00:02.500000+00:00",
        outcome="ok",
        attributes={"gen_ai.usage.input_tokens": 200},
    )


def test_run_is_visible_before_it_finishes(store: RunStore) -> None:
    # APPROVAL-02 seed: `eacp approve <run_id>` must find a paused run from another process.
    run = _run()
    store.start_run(run)
    inflight = store.get_run(run.run_id)
    assert inflight is not None
    assert inflight.status == "running"
    assert inflight.ended_at is None


def test_finish_unknown_run_raises(store: RunStore) -> None:
    with pytest.raises(KeyError):
        store.finish_run("never-started", status="failed", ended_at=T0, metrics={})


def test_orphan_step_rejected(store: RunStore) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        _step(store, "never-started", 0)


def test_duplicate_seq_rejected(store: RunStore) -> None:
    run = _run()
    store.start_run(run)
    _step(store, run.run_id, 0)
    with pytest.raises(sqlite3.IntegrityError):
        _step(store, run.run_id, 0)


def test_store_is_thread_safe(store: RunStore) -> None:
    # CREWAI-03: CrewAI executes on threads. A shared long-lived connection raises here.
    main_run = _run()
    store.start_run(main_run)
    worker_run = _run()
    seen: list[RunRecord | None] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            seen.append(store.get_run(main_run.run_id))
            store.start_run(worker_run)
        except BaseException as exc:  # surfaced on the main thread below
            errors.append(exc)

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert not errors, errors
    assert seen == [main_run]
    assert store.get_run(worker_run.run_id) == worker_run


def test_store_survives_reopen(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "runs.db"  # parent directory does not exist yet
    run = _run()
    SQLiteRunStore(db).start_run(run)

    assert SQLiteRunStore(db).get_run(run.run_id) == run
    with closing(sqlite3.connect(db)) as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert c.execute("PRAGMA user_version").fetchone()[0] == 1


# --- read path and hardening (T-02-06, T-02-10, T-02-11) -----------------------------------


def test_list_runs_filters(store: RunStore) -> None:
    a1 = _run("alpha", "2026-09-25T00:00:00.000000+00:00")
    b1 = _run("beta", "2026-09-26T00:00:00.000000+00:00")
    a2 = _run("alpha", "2026-09-27T00:00:00.000000+00:00")
    for r in (a1, b1, a2):
        store.start_run(r)
    since = "2026-09-26T00:00:00.000000+00:00"

    assert list(store.list_runs()) == [a2, b1, a1]  # everything, newest-first
    assert list(store.list_runs(workflow_id="alpha")) == [a2, a1]
    assert list(store.list_runs(since=since)) == [a2, b1]  # boundary is inclusive
    assert list(store.list_runs(workflow_id="alpha", since=since)) == [a2]
    assert list(store.list_runs(workflow_id="does-not-exist")) == []


def test_filter_value_is_parameterized(store: RunStore) -> None:
    run = _run("alpha")
    store.start_run(run)
    # The benign value must match, or an always-empty list_runs would pass the hostile check.
    assert list(store.list_runs(workflow_id="alpha")) == [run]

    assert list(store.list_runs(workflow_id="alpha'; DROP TABLE runs;--")) == []
    assert list(store.list_runs(workflow_id="alpha' OR '1'='1")) == []
    # Bound, this sorts after every timestamp (no match); interpolated, it would match all.
    assert list(store.list_runs(since="9999' OR '1'='1")) == []
    assert store.get_run(run.run_id) == run  # the table survived


def test_list_runs_limit_is_clamped(tmp_path: Path) -> None:
    db = tmp_path / "runs.db"
    store: RunStore = SQLiteRunStore(db)
    # Bulk-load past the ceiling directly; 1001 start_run calls would only test speed.
    with closing(sqlite3.connect(db)) as c, c:
        c.executemany(
            "INSERT INTO runs (run_id, workflow_id, backend_type, policy_id, policy_hash,"
            " status, started_at, ended_at, metrics) VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (uuid.uuid4().hex, "wf", "langgraph", "p", "h", "succeeded", T0, T0, "{}")
                for _ in range(MAX_LIST_LIMIT + 1)
            ],
        )

    assert len(store.list_runs(limit=10**9)) == MAX_LIST_LIMIT
    assert len(store.list_runs(limit=2)) == 2
    assert len(store.list_runs(limit=0)) == 1
    assert len(store.list_runs(limit=-5)) == 1


def test_store_file_is_not_world_readable(tmp_path: Path) -> None:
    db = tmp_path / "runs.db"
    store = SQLiteRunStore(db)
    # SQLite deletes -wal/-shm when the last connection closes, so hold one open while
    # writing; otherwise the sidecar half of this test asserts against zero files.
    with closing(sqlite3.connect(db)) as holder:
        holder.execute("SELECT count(*) FROM runs").fetchone()
        store.start_run(_run())
        files = sorted(tmp_path.glob("runs.db*"))
        assert {p.name for p in files} >= {"runs.db", "runs.db-wal", "runs.db-shm"}, files
        leaky = {p.name: oct(stat.S_IMODE(p.stat().st_mode)) for p in files}
        assert all(int(m, 8) & 0o077 == 0 for m in leaky.values()), leaky
    assert stat.S_IMODE(db.stat().st_mode) == 0o600
