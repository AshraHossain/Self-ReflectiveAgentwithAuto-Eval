"""BUDGET-01 through BUDGET-04's executable contract for ``SQLiteBudgetLedger``.

Every test uses a real file under ``tmp_path``, never an in-memory database -- the same
connection-per-call reasoning as ``store.py``'s Pitfall 4: a fresh connection to an
in-memory database is a fresh empty database.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from eacp.engine import LlmCall, ToolCall, Usage
from eacp.ledger import SQLiteBudgetLedger
from eacp.policy import Policy, load_yaml_mapping

PolicyYaml = Callable[..., str]


def _policy(text: str) -> Policy:
    return Policy.model_validate(load_yaml_mapping(text))


# --- Task 1: single-process admit()/reconcile() path -----------------------------------


def test_admit_reserves_the_estimate_and_reconcile_applies_the_actual(
    tmp_path: Path, policy_yaml: PolicyYaml
) -> None:
    policy = _policy(policy_yaml())  # max_tokens_per_run=100, mock: in=1, out=2 per Mtok
    ledger = SQLiteBudgetLedger(tmp_path / "ledger.db")

    request = LlmCall("mock", input_tokens=10, max_output_tokens=5)
    admission = ledger.admit("run1", "0", policy, request)

    assert admission.utc_date != ""
    assert admission.estimated_tokens == 15  # 10 input + 5 output
    assert admission.estimated_cost > Decimal(0)
    assert ledger.spent_today(policy.policy_id, admission.utc_date) == admission.estimated_cost

    # Scripted usage deliberately differs from the estimate (Pitfall 5): more input, less
    # output than estimated, so a reconciliation bug that left the estimate alone can fail.
    usage = Usage(input_tokens=20, output_tokens=2, usage_source="provider")
    ledger.reconcile(admission, usage)

    expected_actual_cost = (20 * Decimal(1) + 2 * Decimal(2)) / Decimal(1_000_000)
    spent = ledger.spent_today(policy.policy_id, admission.utc_date)
    assert spent != admission.estimated_cost  # the estimate was replaced, not added to
    assert spent.quantize(Decimal("0.000001")) == expected_actual_cost.quantize(
        Decimal("0.000001")
    )
    assert ledger.run_usage("run1").tokens == 22  # 20 + 2, not 15


def test_tool_call_admission_counts_a_step_but_reserves_no_tokens(
    tmp_path: Path, policy_yaml: PolicyYaml
) -> None:
    policy = _policy(policy_yaml())
    ledger = SQLiteBudgetLedger(tmp_path / "ledger.db")

    admission = ledger.admit("run1", "0", policy, ToolCall("search"))

    assert admission.estimated_tokens == 0
    assert admission.estimated_cost == Decimal(0)
    usage = ledger.run_usage("run1")
    assert usage.steps == 1
    assert usage.tokens == 0
    assert ledger.spent_today(policy.policy_id, admission.utc_date) == Decimal(0)
    # Nothing to reconcile() for a tool call -- no LLM usage was ever estimated.


def test_reopen_reads_back_prior_state(tmp_path: Path, policy_yaml: PolicyYaml) -> None:
    policy = _policy(policy_yaml())
    db = tmp_path / "nested" / "ledger.db"  # parent directory does not exist yet
    first = SQLiteBudgetLedger(db)
    request = LlmCall("mock", input_tokens=10, max_output_tokens=5)
    admission = first.admit("run1", "0", policy, request)

    second = SQLiteBudgetLedger(db)
    assert second.spent_today(policy.policy_id, admission.utc_date) == admission.estimated_cost
    assert second.run_usage("run1").steps == 1

    with closing(sqlite3.connect(db)) as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert c.execute("PRAGMA user_version").fetchone()[0] == 1
