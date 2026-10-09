"""BUDGET-01 through BUDGET-04's executable contract for ``SQLiteBudgetLedger``.

Every test uses a real file under ``tmp_path``, never an in-memory database -- the same
connection-per-call reasoning as ``store.py``'s Pitfall 4: a fresh connection to an
in-memory database is a fresh empty database.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from eacp.engine import LlmCall, ToolCall, Usage
from eacp.errors import PolicyDenied
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


# --- Task 2: deny path, idempotent replay, MISSING usage, cross-midnight reconcile -----


def test_admit_denies_before_the_call_executes_and_changes_nothing(
    tmp_path: Path, policy_yaml: PolicyYaml
) -> None:
    policy = _policy(policy_yaml(max_cost_per_day="0"))
    ledger = SQLiteBudgetLedger(tmp_path / "ledger.db")
    request = LlmCall("mock", input_tokens=100, max_output_tokens=0)

    with pytest.raises(PolicyDenied) as info:
        ledger.admit("run1", "0", policy, request)
    assert info.value.decision.rule == "max_cost_per_day"

    # The transaction rolled back cleanly -- nothing partially committed before the deny
    # was discovered.
    assert ledger.spent_today(policy.policy_id) == Decimal(0)
    usage = ledger.run_usage("run1")
    assert usage.steps == 0
    assert usage.tokens == 0


def test_replayed_admit_is_not_charged_twice(tmp_path: Path, policy_yaml: PolicyYaml) -> None:
    policy = _policy(policy_yaml())
    ledger = SQLiteBudgetLedger(tmp_path / "ledger.db")
    request = LlmCall("mock", input_tokens=10, max_output_tokens=5)

    first = ledger.admit("run1", "0", policy, request)

    # In-flight replay: the reservation exists but has not been reconciled yet.
    replay_in_flight = ledger.admit("run1", "0", policy, request)
    assert replay_in_flight.utc_date == first.utc_date
    assert replay_in_flight.estimated_tokens == first.estimated_tokens
    assert replay_in_flight.estimated_cost == first.estimated_cost
    assert ledger.spent_today(policy.policy_id, first.utc_date) == first.estimated_cost
    assert ledger.run_usage("run1").steps == 1
    assert ledger.run_usage("run1").tokens == first.estimated_tokens

    ledger.reconcile(first, Usage(input_tokens=20, output_tokens=2, usage_source="provider"))
    spent_after_reconcile = ledger.spent_today(policy.policy_id, first.utc_date)
    usage_after_reconcile = ledger.run_usage("run1")

    # Post-reconcile replay: a true replay after completion is also idempotent.
    replay_after_reconcile = ledger.admit("run1", "0", policy, request)
    assert replay_after_reconcile.utc_date == first.utc_date
    assert replay_after_reconcile.estimated_tokens == first.estimated_tokens
    assert replay_after_reconcile.estimated_cost == first.estimated_cost
    assert ledger.spent_today(policy.policy_id, first.utc_date) == spent_after_reconcile
    assert ledger.run_usage("run1") == usage_after_reconcile


def test_max_steps_denies_the_next_call_independent_of_tokens_and_cost(
    tmp_path: Path, policy_yaml: PolicyYaml
) -> None:
    policy = _policy(
        policy_yaml(max_steps=3, max_tokens_per_run=1_000_000, max_cost_per_day="1000000")
    )
    ledger = SQLiteBudgetLedger(tmp_path / "ledger.db")

    ledger.admit("run1", "0", policy, ToolCall("search"))
    ledger.admit("run1", "1", policy, LlmCall("mock", input_tokens=1, max_output_tokens=1))
    ledger.admit("run1", "2", policy, LlmCall("mock", input_tokens=1, max_output_tokens=1))

    with pytest.raises(PolicyDenied) as info:
        ledger.admit("run1", "3", policy, ToolCall("summarize"))
    assert info.value.decision.rule == "max_steps"


def test_missing_usage_charges_the_estimate_not_zero(
    tmp_path: Path, policy_yaml: PolicyYaml
) -> None:
    policy = _policy(policy_yaml())
    ledger = SQLiteBudgetLedger(tmp_path / "ledger.db")
    request = LlmCall("mock", input_tokens=10, max_output_tokens=5)
    admission = ledger.admit("run1", "0", policy, request)

    ledger.reconcile(admission, Usage(None, None, "MISSING"))

    assert ledger.spent_today(policy.policy_id, admission.utc_date) == admission.estimated_cost
    assert ledger.run_usage("run1").tokens == admission.estimated_tokens
    assert ledger.run_usage("run1").missing_usage == 1


def test_reconcile_applies_to_the_admission_date_not_todays_date(
    tmp_path: Path, policy_yaml: PolicyYaml
) -> None:
    dates = [datetime(2026, 1, 1, 23, 59, 59, tzinfo=UTC)]
    policy = _policy(policy_yaml())
    ledger = SQLiteBudgetLedger(tmp_path / "ledger.db", clock=lambda: dates[0])

    request = LlmCall("mock", input_tokens=10, max_output_tokens=5)
    admission = ledger.admit("run1", "0", policy, request)
    assert admission.utc_date == "2026-01-01"

    dates[0] = datetime(2026, 1, 2, 0, 0, 1, tzinfo=UTC)  # crossed midnight, no sleeping
    usage = Usage(input_tokens=20, output_tokens=2, usage_source="provider")
    ledger.reconcile(admission, usage)

    expected = (20 * Decimal(1) + 2 * Decimal(2)) / Decimal(1_000_000)
    exp_quant = expected.quantize(Decimal("0.000001"))
    assert ledger.spent_today(policy.policy_id, "2026-01-01").quantize(
        Decimal("0.000001")
    ) == exp_quant
    assert ledger.spent_today(policy.policy_id, "2026-01-02") == Decimal(0)


def test_double_reconcile_raises_keyerror(tmp_path: Path, policy_yaml: PolicyYaml) -> None:
    policy = _policy(policy_yaml())
    ledger = SQLiteBudgetLedger(tmp_path / "ledger.db")
    request = LlmCall("mock", input_tokens=10, max_output_tokens=5)
    admission = ledger.admit("run1", "0", policy, request)
    usage = Usage(input_tokens=20, output_tokens=2, usage_source="provider")
    ledger.reconcile(admission, usage)
    spent_after_first = ledger.spent_today(policy.policy_id, admission.utc_date)

    with pytest.raises(KeyError):
        ledger.reconcile(admission, usage)

    assert ledger.spent_today(policy.policy_id, admission.utc_date) == spent_after_first
