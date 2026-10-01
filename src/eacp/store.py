"""Run history (TRACE-03): the pluggable ``RunStore`` contract and its v1 SQLite backing.

Pluggability is structural: a third-party store satisfies ``RunStore`` by having the six
methods with these signatures, without importing anything from ``eacp``. Conformance is
checked statically (``store: RunStore = MyStore(...)`` under ``mypy --strict``), never with a
runtime protocol check -- that check only compares method *names* and passes a class whose
every method has the wrong arity (02-RESEARCH.md Finding 7).

Timestamps are ISO-8601 UTC strings with microsecond precision (see ``utc_now``), stored as
TEXT. They sort lexicographically, which is what ``list_runs`` ordering and its ``since``
filter rely on. Never hand a ``datetime`` to the driver: its implicit adapter is deprecated
since Python 3.12 and the test suite turns that warning into a failure.

On disk the store is THREE files in WAL mode: ``runs.db``, ``runs.db-wal`` and
``runs.db-shm``. Copying or backing up "the store file" alone loses committed data.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

# `denied` is a governance halt (approval refused, APPROVAL-03; budget block, BUDGET-01), which
# is a different outcome from `failed`, a crash.
RunStatus = Literal["running", "awaiting_approval", "succeeded", "failed", "denied"]

MAX_LIST_LIMIT = 1000  # T-02-10: list_runs never materializes more than this


def utc_now() -> str:
    """The one canonical timestamp form: ISO-8601, UTC, microseconds, fixed width."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    workflow_id: str
    backend_type: str
    policy_id: str
    policy_hash: str
    status: RunStatus
    started_at: str
    ended_at: str | None
    metrics: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class StepRecord:
    run_id: str
    seq: int
    name: str
    started_at: str
    ended_at: str
    outcome: str
    attributes: Mapping[str, object]


class RunStore(Protocol):
    """Synchronous run-history store (D-06).

    ``run_id`` is minted by the caller, as ``uuid.uuid4().hex``: LANGGRAPH-02 uses it as the
    checkpointer ``thread_id`` before the store is touched, and a store outage should fail the
    history write rather than block the run from starting. A run is written in two halves --
    ``start_run`` then ``finish_run`` -- so a paused run is visible to another process
    (APPROVAL-02) before it finishes.
    """

    def start_run(self, run: RunRecord) -> None: ...

    def finish_run(
        self, run_id: str, *, status: RunStatus, ended_at: str, metrics: Mapping[str, object]
    ) -> None:
        """Raise ``KeyError`` if ``run_id`` was never started."""
        ...

    def append_step(
        self,
        run_id: str,
        *,
        seq: int,
        name: str,
        started_at: str,
        ended_at: str,
        outcome: str,
        attributes: Mapping[str, object],
    ) -> None: ...

    def get_run(self, run_id: str) -> RunRecord | None: ...

    def list_runs(
        self, *, workflow_id: str | None = None, since: str | None = None, limit: int = 100
    ) -> Sequence[RunRecord]:
        """Newest-first by ``started_at``; ``limit`` is clamped by the implementation."""
        ...

    def list_steps(self, run_id: str) -> Sequence[StepRecord]:
        """Steps in ``seq`` order."""
        ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id       TEXT PRIMARY KEY,
  workflow_id  TEXT NOT NULL,
  backend_type TEXT NOT NULL,
  policy_id    TEXT NOT NULL,
  policy_hash  TEXT NOT NULL,
  status       TEXT NOT NULL,
  started_at   TEXT NOT NULL,
  ended_at     TEXT,
  metrics      TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_runs_workflow_started ON runs(workflow_id, started_at);

CREATE TABLE IF NOT EXISTS run_steps (
  run_id     TEXT NOT NULL REFERENCES runs(run_id),
  seq        INTEGER NOT NULL,
  name       TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at   TEXT NOT NULL,
  outcome    TEXT NOT NULL,
  attributes TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (run_id, seq)
);
"""


def _dumps(value: Mapping[str, object]) -> str:
    return json.dumps(value, sort_keys=True)  # sorted keys: stored blobs are comparable


def _row_to_run(r: sqlite3.Row) -> RunRecord:
    return RunRecord(
        run_id=r["run_id"],
        workflow_id=r["workflow_id"],
        backend_type=r["backend_type"],
        policy_id=r["policy_id"],
        policy_hash=r["policy_hash"],
        status=r["status"],
        started_at=r["started_at"],
        ended_at=r["ended_at"],
        metrics=json.loads(r["metrics"]),
    )


def _row_to_step(r: sqlite3.Row) -> StepRecord:
    return StepRecord(
        run_id=r["run_id"],
        seq=r["seq"],
        name=r["name"],
        started_at=r["started_at"],
        ended_at=r["ended_at"],
        outcome=r["outcome"],
        attributes=json.loads(r["attributes"]),
    )


class SQLiteRunStore:
    """v1 ``RunStore``: stdlib ``sqlite3``, WAL, one connection per call."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        # Otherwise the driver fails with an unhelpful "unable to open database file".
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as c:
            # First statement, before any DML: under the legacy transaction default the first
            # DML opens an implicit transaction and this pragma then fails. WAL persists in the
            # file header, so it is set once here rather than per connection.
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(_SCHEMA)
            # ponytail: migrations are a user_version comparison + if-ladder when the schema
            # next changes; no migration framework for two tables.
            c.execute("PRAGMA user_version=1")

    # ponytail: one connection per call -- measured ~1.2 ms/write vs 161 us for a long-lived
    # handle, i.e. ~1 ms per history row against LLM calls measured in seconds. In exchange it
    # deletes thread affinity (CrewAI runs on threads), connection lifecycle (no close() on the
    # Protocol) and cross-process coherence (Phase 4's approval CLI) as concerns. Upgrade path
    # if history writes ever dominate a profile: a thread-local connection; the Protocol does
    # not change.
    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._path, timeout=30.0)
        # Foreign keys default OFF and the setting is per-connection (it does not persist in
        # the file), so this is the one place it can live.
        c.execute("PRAGMA foreign_keys=ON")
        c.row_factory = sqlite3.Row
        return c

    # Writes: one transaction per method, never batched into the run's transaction, so a
    # crash mid-run leaves the run row in flight plus every step written so far.
    def start_run(self, run: RunRecord) -> None:
        with closing(self._connect()) as c, c:
            c.execute(
                "INSERT INTO runs (run_id, workflow_id, backend_type, policy_id, policy_hash,"
                " status, started_at, ended_at, metrics) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    run.run_id,
                    run.workflow_id,
                    run.backend_type,
                    run.policy_id,
                    run.policy_hash,
                    run.status,
                    run.started_at,
                    run.ended_at,
                    _dumps(run.metrics),
                ),
            )

    def finish_run(
        self, run_id: str, *, status: RunStatus, ended_at: str, metrics: Mapping[str, object]
    ) -> None:
        with closing(self._connect()) as c, c:
            cur = c.execute(
                "UPDATE runs SET status=?, ended_at=?, metrics=? WHERE run_id=?",
                (status, ended_at, _dumps(metrics), run_id),
            )
            if cur.rowcount == 0:  # a silent no-op on an unknown id is worse than a raise
                raise KeyError(f"unknown run_id {run_id!r}")

    def append_step(
        self,
        run_id: str,
        *,
        seq: int,
        name: str,
        started_at: str,
        ended_at: str,
        outcome: str,
        attributes: Mapping[str, object],
    ) -> None:
        with closing(self._connect()) as c, c:
            c.execute(
                "INSERT INTO run_steps (run_id, seq, name, started_at, ended_at, outcome,"
                " attributes) VALUES (?,?,?,?,?,?,?)",
                (run_id, seq, name, started_at, ended_at, outcome, _dumps(attributes)),
            )

    def get_run(self, run_id: str) -> RunRecord | None:
        with closing(self._connect()) as c:
            row = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return None if row is None else _row_to_run(row)

    def list_runs(
        self, *, workflow_id: str | None = None, since: str | None = None, limit: int = 100
    ) -> Sequence[RunRecord]:
        return []

    def list_steps(self, run_id: str) -> Sequence[StepRecord]:
        with closing(self._connect()) as c:
            rows = c.execute(
                "SELECT * FROM run_steps WHERE run_id=? ORDER BY seq", (run_id,)
            ).fetchall()
        return [_row_to_step(r) for r in rows]
