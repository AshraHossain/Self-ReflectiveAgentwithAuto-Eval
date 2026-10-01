"""Run history (TRACE-03). RED skeleton: interface only, behaviour lands in GREEN."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

RunStatus = Literal["running", "awaiting_approval", "succeeded", "failed", "denied"]


def utc_now() -> str:
    return ""


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
    def start_run(self, run: RunRecord) -> None: ...

    def finish_run(
        self, run_id: str, *, status: RunStatus, ended_at: str, metrics: Mapping[str, object]
    ) -> None: ...

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
    ) -> Sequence[RunRecord]: ...

    def list_steps(self, run_id: str) -> Sequence[StepRecord]: ...


class SQLiteRunStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def start_run(self, run: RunRecord) -> None:
        return None

    def finish_run(
        self, run_id: str, *, status: RunStatus, ended_at: str, metrics: Mapping[str, object]
    ) -> None:
        return None

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
        return None

    def get_run(self, run_id: str) -> RunRecord | None:
        return None

    def list_runs(
        self, *, workflow_id: str | None = None, since: str | None = None, limit: int = 100
    ) -> Sequence[RunRecord]:
        return []

    def list_steps(self, run_id: str) -> Sequence[StepRecord]:
        return []
