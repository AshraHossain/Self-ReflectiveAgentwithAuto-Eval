"""SQLite-backed, cross-process-safe budget ledger (BUDGET-01/02/03/04): ``SQLiteBudgetLedger``.

On disk this is a SEPARATE file from ``runs.db`` -- ``ledger.db`` plus its ``-wal``/``-shm``
sidecars, the project's second persistent artifact. Both files set ``PRAGMA user_version=1``;
sharing one file between the two stores would give two independent schemas one migration
marker, so ``ledger.db`` is never shared with ``runs.db``. Like ``store.py`` this is THREE
files in WAL mode and is made owner-read/write only (0600) before the first connect; SQLite
creates the ``-wal``/``-shm`` sidecars with the database file's own permissions.

The one deliberate divergence from ``store.py`` is the transaction style. ``admit()`` reads
budget state, calls the pure ``eacp.engine.decide()``, and writes a reservation -- a
check-then-reserve sequence that ``store.py``'s ``with closing(self._connect()) as c, c:``
(the driver's legacy implicit-transaction mode) gets badly wrong under real concurrency: a
4-process probe recorded 20-39 admissions against a cap of 10 (03-RESEARCH.md Pitfall 1),
because the legacy driver opens a transaction only before INSERT/UPDATE/DELETE/REPLACE, never
before the SELECT that reads state -- every reader sees the same stale headroom and every one
reserves. Even the tempting one-word fix, ``isolation_level="IMMEDIATE"`` without ``None``, is
*also* wrong: it stays in legacy mode and the SELECT still runs unprotected (measured 107
admitted against a cap of 100, 03-RESEARCH.md Addendum G-2). ``isolation_level=None`` plus an
explicit ``BEGIN IMMEDIATE`` issued before the read was exact -- 10 of 10, then separately 100
of 100 -- in every probe run. Every connection this module opens, read or write, uses
``isolation_level=None``; there is no second transaction style to accidentally fall back to.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from eacp.engine import (
    BudgetState,
    Decision,
    LlmCall,
    ToolCall,
    Usage,
    cost_of,
    decide,
    output_estimate,
)
from eacp.errors import PolicyDenied
from eacp.policy import ModelPrice, Policy

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_spend (
  policy_id TEXT NOT NULL,
  utc_date  TEXT NOT NULL,          -- date.isoformat(), never a date object (deprecated adapter)
  spent     TEXT NOT NULL,          -- str(Decimal), never REAL
  PRIMARY KEY (policy_id, utc_date)
);
CREATE TABLE IF NOT EXISTS run_usage (
  run_id        TEXT PRIMARY KEY,
  steps         INTEGER NOT NULL,
  tokens        INTEGER NOT NULL,
  missing_usage INTEGER NOT NULL DEFAULT 0   -- BUDGET-05: runs with a MISSING reading
);
CREATE TABLE IF NOT EXISTS reservations (
  run_id                TEXT NOT NULL,
  call_key              TEXT NOT NULL,
  policy_id             TEXT NOT NULL,
  utc_date              TEXT NOT NULL,
  tokens                INTEGER NOT NULL,
  cost                  TEXT NOT NULL,
  reconciled            INTEGER NOT NULL DEFAULT 0,
  -- G-1: the price pinned at admission time, so reconcile() (which takes no policy
  -- argument) can still compute the actual cost after the fact. NULL for a ToolCall
  -- reservation, which has no LLM usage to ever reconcile.
  price_input_per_mtok  TEXT,
  price_output_per_mtok TEXT,
  PRIMARY KEY (run_id, call_key)
);
"""


@dataclass(frozen=True, slots=True)
class Admission:
    """What ``admit()`` returns on allow: the ``Decision`` that allowed it, plus everything
    needed to reconcile the reservation later without a second lookup."""

    decision: Decision
    run_id: str
    call_key: str
    utc_date: str
    estimated_tokens: int
    estimated_cost: Decimal


@dataclass(frozen=True, slots=True)
class RunUsage:
    steps: int
    tokens: int
    missing_usage: int


def _replay_decision(policy: Policy, request: LlmCall | ToolCall, row: sqlite3.Row) -> Decision:
    # A stored reservation is only ever the record of a prior ALLOW -- a deny rolls the
    # transaction back before any INSERT runs -- so a replay's decision is always "allow".
    # limit/observed are recomputed from the current policy + request rather than persisted
    # a second time: nothing downstream depends on byte-for-byte replay fidelity of this
    # informational field, only on budget/step state never double-charging (G-1).
    if isinstance(request, ToolCall):
        return Decision(
            outcome="allow",
            policy_id=policy.policy_id,
            version=policy.version,
            rule="allowed_tools",
            limit=tuple(policy.allowed_tools),
            observed=request.tool_name,
        )
    return Decision(
        outcome="allow",
        policy_id=policy.policy_id,
        version=policy.version,
        rule="max_cost_per_day",
        limit=policy.max_cost_per_day,
        observed=Decimal(row["cost"]),
    )


class SQLiteBudgetLedger:
    """v1 budget ledger: stdlib ``sqlite3``, WAL, one connection per call.

    ``admit()``/``reconcile()`` run inside ``_tx()``'s ``BEGIN IMMEDIATE`` transaction;
    everything else is a plain unlocked read -- it does not gate a decision, so it needs no
    lock. ponytail: one connection per call (store.py's own measured ~1ms/call ceiling
    applies here too and is negligible next to an LLM call; G-4 measured 2.76ms for a whole
    admit+reconcile pair). Upgrade path if this ever profiles hot: a thread-local
    connection -- the public methods below do not change.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # T-03-08: restrict BEFORE the first connect -- SQLite creates the -wal/-shm
        # sidecars with the database file's own mode, so this one call covers all three.
        self._path.touch(mode=0o600, exist_ok=True)
        self._path.chmod(0o600)
        self._clock = clock
        with closing(self._connect()) as c:
            # First statement, before any DML: the pragma persists in the file header, so
            # it is set once here rather than per connection.
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(_SCHEMA)
            # ponytail: migrations are a user_version comparison + if-ladder when the
            # schema next changes; no migration framework for three tables.
            c.execute("PRAGMA user_version=1")

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None everywhere in this module, reads included: the only way to
        # guarantee no code path quietly reintroduces the legacy implicit-transaction mode
        # that over-admitted 2-4x (Pitfall 1) is to never open a connection in it at all.
        c = sqlite3.connect(self._path, timeout=30.0, isolation_level=None)
        c.row_factory = sqlite3.Row
        return c

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        c = self._connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.execute("COMMIT")
        except BaseException:
            # Pitfall 7: BEGIN IMMEDIATE itself can fail (a busy timeout) before any
            # transaction opens; rolling back one that was never opened raises a second,
            # misleading error that masks the real cause.
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise
        finally:
            c.close()

    def admit(
        self, run_id: str, call_key: str, policy: Policy, request: LlmCall | ToolCall
    ) -> Admission:
        with self._tx() as c:
            existing = c.execute(
                "SELECT utc_date, tokens, cost FROM reservations WHERE run_id=? AND call_key=?",
                (run_id, call_key),
            ).fetchone()
            if existing is not None:
                # G-1: an existing row -- in flight or already reconciled -- short-circuits
                # admit() without re-running decide() or charging anything again.
                return Admission(
                    decision=_replay_decision(policy, request, existing),
                    run_id=run_id,
                    call_key=call_key,
                    utc_date=existing["utc_date"],
                    estimated_tokens=existing["tokens"],
                    estimated_cost=Decimal(existing["cost"]),
                )

            run_row = c.execute(
                "SELECT steps, tokens FROM run_usage WHERE run_id=?", (run_id,)
            ).fetchone()
            steps_taken = run_row["steps"] if run_row is not None else 0
            run_tokens = run_row["tokens"] if run_row is not None else 0

            utc_date = self._clock().date().isoformat()
            spend_row = c.execute(
                "SELECT spent FROM daily_spend WHERE policy_id=? AND utc_date=?",
                (policy.policy_id, utc_date),
            ).fetchone()
            spent_today = Decimal(spend_row["spent"]) if spend_row is not None else Decimal(0)

            state = BudgetState(
                steps_taken=steps_taken, run_tokens=run_tokens, spent_today=spent_today
            )
            decision = decide(policy, request, state)
            if decision.outcome == "deny":
                # The `with` block's exception propagates into _tx()'s except, which rolls
                # the transaction back before this raises -- the call never executes and no
                # partial state (steps/tokens/spend) is left behind.
                raise PolicyDenied(decision)

            price_in: str | None
            price_out: str | None
            if isinstance(request, ToolCall):
                # BUDGET-04: a tool call counts a step but reserves no tokens/cost -- there
                # is nothing to reconcile() for it (no LLM usage was ever estimated).
                est_tokens = 0
                est_cost = Decimal(0)
                price_in = price_out = None
            else:
                out = output_estimate(policy, request, state)
                est_tokens = request.input_tokens + out
                price = policy.model_prices[request.model]  # decide() already confirmed it
                est_cost = cost_of(price, request.input_tokens, out)
                price_in = str(price.input_per_mtok)
                price_out = str(price.output_per_mtok)

            new_steps = steps_taken + 1
            new_tokens = run_tokens + est_tokens
            if run_row is None:
                c.execute(
                    "INSERT INTO run_usage (run_id, steps, tokens, missing_usage)"
                    " VALUES (?,?,?,0)",
                    (run_id, new_steps, new_tokens),
                )
            else:
                c.execute(
                    "UPDATE run_usage SET steps=?, tokens=? WHERE run_id=?",
                    (new_steps, new_tokens, run_id),
                )

            if not isinstance(request, ToolCall):
                new_spent = spent_today + est_cost
                if spend_row is None:
                    c.execute(
                        "INSERT INTO daily_spend (policy_id, utc_date, spent) VALUES (?,?,?)",
                        (policy.policy_id, utc_date, str(new_spent)),
                    )
                else:
                    c.execute(
                        "UPDATE daily_spend SET spent=? WHERE policy_id=? AND utc_date=?",
                        (str(new_spent), policy.policy_id, utc_date),
                    )

            c.execute(
                "INSERT INTO reservations (run_id, call_key, policy_id, utc_date, tokens,"
                " cost, reconciled, price_input_per_mtok, price_output_per_mtok)"
                " VALUES (?,?,?,?,?,?,0,?,?)",
                (
                    run_id,
                    call_key,
                    policy.policy_id,
                    utc_date,
                    est_tokens,
                    str(est_cost),
                    price_in,
                    price_out,
                ),
            )

            return Admission(
                decision=decision,
                run_id=run_id,
                call_key=call_key,
                utc_date=utc_date,
                estimated_tokens=est_tokens,
                estimated_cost=est_cost,
            )

    def reconcile(self, admission: Admission, usage: Usage) -> None:
        with self._tx() as c:
            cur = c.execute(
                "UPDATE reservations SET reconciled=1"
                " WHERE run_id=? AND call_key=? AND reconciled=0",
                (admission.run_id, admission.call_key),
            )
            if cur.rowcount == 0:
                # Copies store.py's "a silent no-op on an unknown id is worse than a raise"
                # convention (store.py line 233): an unknown call_key and an
                # already-reconciled one are indistinguishable here, and both must raise.
                raise KeyError(
                    f"unknown or already-reconciled reservation"
                    f" (run_id={admission.run_id!r}, call_key={admission.call_key!r})"
                )

            row = c.execute(
                "SELECT policy_id, utc_date, tokens, cost, price_input_per_mtok,"
                " price_output_per_mtok FROM reservations WHERE run_id=? AND call_key=?",
                (admission.run_id, admission.call_key),
            ).fetchone()
            assert row is not None  # the UPDATE above just matched exactly this row

            est_tokens = row["tokens"]
            est_cost = Decimal(row["cost"])

            if usage.usage_source == "MISSING":
                # BUDGET-05: charge the estimate, never zero -- the delta is zero, not a
                # zero charge replacing the estimate.
                actual_tokens = est_tokens
                actual_cost = est_cost
                missing_delta = 1
            else:
                # Usage.__post_init__ guarantees both counts are present (not None) for
                # every usage_source other than "MISSING".
                assert usage.input_tokens is not None and usage.output_tokens is not None
                price = ModelPrice(
                    input_per_mtok=Decimal(row["price_input_per_mtok"]),
                    output_per_mtok=Decimal(row["price_output_per_mtok"]),
                )
                actual_tokens = usage.input_tokens + usage.output_tokens
                actual_cost = cost_of(price, usage.input_tokens, usage.output_tokens)
                missing_delta = 0

            token_delta = actual_tokens - est_tokens
            cost_delta = actual_cost - est_cost

            c.execute(
                "UPDATE run_usage SET tokens=tokens+?, missing_usage=missing_usage+?"
                " WHERE run_id=?",
                (token_delta, missing_delta, admission.run_id),
            )

            # Pitfall 3: correct the admission's OWN utc_date, never today's -- a call
            # admitted at 23:59:59 UTC and reconciled after midnight must still correct the
            # day it was charged to.
            policy_id = row["policy_id"]
            utc_date = row["utc_date"]
            spend_row = c.execute(
                "SELECT spent FROM daily_spend WHERE policy_id=? AND utc_date=?",
                (policy_id, utc_date),
            ).fetchone()
            current_spent = Decimal(spend_row["spent"]) if spend_row is not None else Decimal(0)
            new_spent = current_spent + cost_delta
            if spend_row is None:
                c.execute(
                    "INSERT INTO daily_spend (policy_id, utc_date, spent) VALUES (?,?,?)",
                    (policy_id, utc_date, str(new_spent)),
                )
            else:
                c.execute(
                    "UPDATE daily_spend SET spent=? WHERE policy_id=? AND utc_date=?",
                    (str(new_spent), policy_id, utc_date),
                )

    def spent_today(self, policy_id: str, utc_date: str | None = None) -> Decimal:
        date_ = utc_date if utc_date is not None else self._clock().date().isoformat()
        with closing(self._connect()) as c:
            row = c.execute(
                "SELECT spent FROM daily_spend WHERE policy_id=? AND utc_date=?",
                (policy_id, date_),
            ).fetchone()
        return Decimal(row["spent"]) if row is not None else Decimal(0)

    def run_usage(self, run_id: str) -> RunUsage:
        with closing(self._connect()) as c:
            row = c.execute(
                "SELECT steps, tokens, missing_usage FROM run_usage WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if row is None:
            return RunUsage(steps=0, tokens=0, missing_usage=0)
        return RunUsage(
            steps=row["steps"], tokens=row["tokens"], missing_usage=row["missing_usage"]
        )
