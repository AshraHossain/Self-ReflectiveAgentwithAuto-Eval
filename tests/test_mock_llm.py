"""Success criterion 4 (keyless, scripted, non-zero-usage mock) and the BUDGET-01/04/05
end-to-end integration proof: the mock driven through a REAL ``SQLiteBudgetLedger``.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest

from eacp.engine import LlmCall, Usage
from eacp.ledger import SQLiteBudgetLedger
from eacp.mock_llm import MockLLM, MockToolCall, MockTurn
from eacp.policy import Policy, load_yaml_mapping

PolicyYaml = Callable[..., str]


def _policy(text: str) -> Policy:
    return Policy.model_validate(load_yaml_mapping(text))


# --- Task 1: MockLLM core, wired end-to-end through the real ledger -------------------


def test_mock_emits_scripted_turns_in_order_with_nonzero_usage() -> None:
    turns = (
        MockTurn(text="hello"),
        MockTurn(text="", tool_calls=(MockToolCall(name="search", args={"q": "x"}),)),
    )
    mock = MockLLM(turns)

    first = mock.complete([])
    second = mock.complete([])

    assert first is turns[0]
    assert second is turns[1]
    assert first.text == "hello"
    assert second.tool_calls == (MockToolCall(name="search", args={"q": "x"}),)
    for turn in (first, second):
        assert turn.usage.usage_source == "provider"
        assert turn.usage.input_tokens is not None and turn.usage.input_tokens > 0
        assert turn.usage.output_tokens is not None and turn.usage.output_tokens > 0


def test_mock_script_exhaustion_raises() -> None:
    mock = MockLLM([MockTurn(text="only")])
    mock.complete([])

    with pytest.raises(RuntimeError, match=r"exhausted after 1 call"):
        mock.complete([])


def test_mock_is_keyless(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, policy_yaml: PolicyYaml
) -> None:
    # Explicit success criterion 4: not "the test happens to pass when these vars are
    # unset" but "the mock never reads them" -- proven by deleting both, then driving the
    # SAME full scripted-through-a-real-ledger scenario as the tracer proof below.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    policy = _policy(policy_yaml())
    ledger = SQLiteBudgetLedger(tmp_path / "ledger.db")
    mock = MockLLM([MockTurn(usage=Usage(20, 2, "provider"))])
    request = LlmCall("mock", input_tokens=10, max_output_tokens=5)

    admission = ledger.admit("run1", "0", policy, request)
    turn = mock.complete([])
    ledger.reconcile(admission, turn.usage)

    assert turn.usage.input_tokens is not None and turn.usage.input_tokens > 0
    assert turn.usage.output_tokens is not None and turn.usage.output_tokens > 0
    assert ledger.spent_today(policy.policy_id, admission.utc_date) > Decimal(0)


def test_mock_turns_flow_through_a_real_ledger(
    tmp_path: Path, policy_yaml: PolicyYaml
) -> None:
    # Default fixture policy already prices "mock" at {input: 1, output: 2} per Mtok
    # (tests/conftest.py's _VALID_POLICY).
    policy = _policy(policy_yaml())
    ledger = SQLiteBudgetLedger(tmp_path / "ledger.db")

    # Pitfall 5: scripted usage is chosen to differ from what estimate_tokens()/the
    # pre-call reservation would produce for this same request (input=10, max_output=5 ->
    # a 15-token, 0.000020 estimate), so a reconciliation bug that left the estimate alone
    # would be caught, not hidden behind an accidental match.
    script = (
        MockTurn(usage=Usage(20, 2, "provider")),
        MockTurn(usage=Usage(5, 30, "provider")),
    )
    mock = MockLLM(script)
    request = LlmCall("mock", input_tokens=10, max_output_tokens=5)

    admission_1 = ledger.admit("run1", "0", policy, request)
    assert admission_1.estimated_tokens == 15
    turn_1 = mock.complete([])
    ledger.reconcile(admission_1, turn_1.usage)

    admission_2 = ledger.admit("run1", "1", policy, request)
    turn_2 = mock.complete([])
    ledger.reconcile(admission_2, turn_2.usage)

    expected_cost = (
        (20 * Decimal(1) + 2 * Decimal(2)) + (5 * Decimal(1) + 30 * Decimal(2))
    ) / Decimal(1_000_000)
    spent = ledger.spent_today(policy.policy_id, admission_1.utc_date)
    assert spent.quantize(Decimal("0.000001")) == expected_cost.quantize(Decimal("0.000001"))
    # Reflects the SCRIPTED usage (22 + 35 = 57 tokens), not the 30-token pre-call estimate.
    assert ledger.run_usage("run1").tokens == 57
