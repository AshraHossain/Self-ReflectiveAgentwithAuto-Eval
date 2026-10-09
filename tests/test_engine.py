"""POLICY-03 and BUDGET-05's executable contract for the pure decision core."""

import ast
import pathlib
from collections.abc import Callable
from decimal import Decimal

import pytest

import eacp.engine
from eacp.engine import BudgetState, Decision, LlmCall, ToolCall, Usage, decide, output_estimate
from eacp.errors import PolicyDenied
from eacp.policy import COST_EXP, Policy, load_yaml_mapping

PolicyYaml = Callable[..., str]


def _policy(text: str) -> Policy:
    return Policy.model_validate(load_yaml_mapping(text))


def test_decide_returns_a_structured_decision(policy_yaml: PolicyYaml) -> None:
    """Tracer proof: YAML -> Policy -> decide() -> Decision, end to end.

    Deliberately not exhaustive -- Task 2 owns the boundary/semantic exhaustiveness. This
    test's job is to prove the vertical slice works for one allowed and one denied case of
    each request type, with every Decision field populated and never a bare boolean.
    """
    policy = _policy(policy_yaml())
    state = BudgetState(steps_taken=0, run_tokens=0, spent_today=Decimal("0"))

    allowed_llm = decide(policy, LlmCall("mock", input_tokens=10, max_output_tokens=5), state)
    assert allowed_llm.outcome == "allow", allowed_llm
    assert allowed_llm.policy_id == policy.policy_id
    assert allowed_llm.version == policy.version
    assert isinstance(allowed_llm, Decision)

    unpriced = LlmCall("unpriced-model", input_tokens=10, max_output_tokens=5)
    denied_llm = decide(policy, unpriced, state)
    assert denied_llm.outcome == "deny", denied_llm
    assert denied_llm.rule == "model_prices"
    assert denied_llm.observed == "unpriced-model"

    allowed_tool = decide(policy, ToolCall("search"), state)
    assert allowed_tool.outcome == "allow", allowed_tool
    assert allowed_tool.rule == "allowed_tools"

    denied_tool = decide(policy, ToolCall("send_email"), state)
    assert denied_tool.outcome == "deny", denied_tool
    assert denied_tool.rule == "forbidden_tools"
    assert denied_tool.observed == "send_email"

    for decision in (allowed_llm, denied_llm, allowed_tool, denied_tool):
        assert decision.outcome in ("allow", "deny")
        assert decision.rule is not None
        assert decision.limit is not None or decision.limit == 0
        assert decision.observed is not None


# --- Task 2: exhaustive decide() correctness -------------------------------------------


@pytest.mark.parametrize(
    ("rule", "offset"),
    [
        ("max_steps", -1),
        ("max_steps", 0),
        ("max_steps", 1),
        ("max_tokens_per_run", -1),
        ("max_tokens_per_run", 0),
        ("max_tokens_per_run", 1),
        ("max_cost_per_day", -1),
        ("max_cost_per_day", 0),
        ("max_cost_per_day", 1),
    ],
)
def test_numeric_deny_iff_observed_exceeds_limit(
    policy_yaml: PolicyYaml, rule: str, offset: int
) -> None:
    """POLICY-03's one invariant, proven at the boundary for all three numeric rules:
    outcome == 'deny' if and only if the projected observed value exceeds the limit."""
    policy = _policy(policy_yaml())
    zero_call = LlmCall("mock", input_tokens=0, max_output_tokens=0)  # cost_of(...) == 0

    if rule == "max_steps":
        state = BudgetState(
            steps_taken=policy.max_steps - 1 + offset, run_tokens=0, spent_today=Decimal(0)
        )
        decision = decide(policy, ToolCall("search"), state)
        expect_deny = offset > 0
    elif rule == "max_tokens_per_run":
        state = BudgetState(
            steps_taken=0, run_tokens=policy.max_tokens_per_run + offset, spent_today=Decimal(0)
        )
        decision = decide(policy, zero_call, state)
        expect_deny = offset > 0
    else:
        spent = policy.max_cost_per_day + offset * COST_EXP
        state = BudgetState(steps_taken=0, run_tokens=0, spent_today=spent)
        decision = decide(policy, zero_call, state)
        expect_deny = offset > 0

    assert (decision.outcome == "deny") is expect_deny, (
        f"{rule} offset={offset}: got {decision.outcome}, rule={decision.rule}, "
        f"limit={decision.limit}, observed={decision.observed}"
    )
    if expect_deny:
        assert decision.rule == rule, decision


def test_forbidden_tools_beats_allowed_tools(policy_yaml: PolicyYaml) -> None:
    policy = _policy(policy_yaml(allowed_tools=["search", "summarize", "send_email"]))
    state = BudgetState(steps_taken=0, run_tokens=0, spent_today=Decimal(0))
    decision = decide(policy, ToolCall("send_email"), state)
    assert decision.outcome == "deny", decision
    assert decision.rule == "forbidden_tools", decision


def test_empty_allowed_tools_denies_every_tool(policy_yaml: PolicyYaml) -> None:
    policy = _policy(policy_yaml(allowed_tools=[]))
    state = BudgetState(steps_taken=0, run_tokens=0, spent_today=Decimal(0))
    decision = decide(policy, ToolCall("search"), state)
    assert decision.outcome == "deny", decision
    assert decision.rule == "allowed_tools", decision


def test_unpriced_model_is_denied(policy_yaml: PolicyYaml) -> None:
    policy = _policy(policy_yaml())
    state = BudgetState(steps_taken=0, run_tokens=0, spent_today=Decimal(0))
    request = LlmCall("totally-unpriced", input_tokens=10, max_output_tokens=5)
    decision = decide(policy, request, state)
    assert decision.outcome == "deny", decision
    assert decision.rule == "model_prices", decision
    assert decision.observed == "totally-unpriced", decision


def test_max_steps_is_checked_before_tokens_or_cost(policy_yaml: PolicyYaml) -> None:
    """BUDGET-04 independence: max_steps denies even with enormous token/cost headroom,
    for both an LlmCall and a ToolCall."""
    policy = _policy(
        policy_yaml(max_tokens_per_run=1_000_000, max_cost_per_day="1000000")
    )
    state = BudgetState(steps_taken=policy.max_steps, run_tokens=0, spent_today=Decimal(0))

    llm_decision = decide(policy, LlmCall("mock", input_tokens=1, max_output_tokens=1), state)
    assert llm_decision.outcome == "deny", llm_decision
    assert llm_decision.rule == "max_steps", llm_decision

    tool_decision = decide(policy, ToolCall("search"), state)
    assert tool_decision.outcome == "deny", tool_decision
    assert tool_decision.rule == "max_steps", tool_decision


def test_usage_missing_requires_no_counts() -> None:
    usage = Usage(None, None, "MISSING")
    assert usage.input_tokens is None
    assert usage.output_tokens is None


def test_usage_provider_requires_both_counts() -> None:
    usage = Usage(0, 0, "provider")
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    with pytest.raises(ValueError, match="MISSING usage carries no counts"):
        Usage(5, None, "provider")
    with pytest.raises(ValueError, match="MISSING usage carries no counts"):
        Usage(5, 5, "MISSING")


def test_usage_rejects_negative_counts() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        Usage(-1, 0, "provider")


def test_usage_rejects_bool_counts() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        Usage(True, 0, "provider")


def test_output_estimate_fills_remaining_run_tokens(policy_yaml: PolicyYaml) -> None:
    """A5: with no caller-supplied max_output_tokens, the output estimate equals the run's
    remaining token headroom -- not zero and not unbounded."""
    policy = _policy(policy_yaml(max_tokens_per_run=100))
    state = BudgetState(steps_taken=0, run_tokens=20, spent_today=Decimal(0))
    request = LlmCall("mock", input_tokens=30, max_output_tokens=None)
    out = output_estimate(policy, request, state)
    assert out == 100 - 20 - 30 == 50, out


def test_engine_imports_are_pure() -> None:
    """The AST walk from 03-RESEARCH.md, resolving eacp.engine.__file__ so the test is
    correct regardless of the invoking working directory."""
    allowed = {"__future__", "math", "dataclasses", "decimal", "typing", "eacp.policy"}
    tree = ast.parse(pathlib.Path(eacp.engine.__file__).read_text())
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
        elif isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
    assert mods <= allowed, f"engine.py imports outside the pure allowlist: {mods - allowed}"


# --- Task 3: PolicyDenied ---------------------------------------------------------------


def test_policy_denied_carries_the_decision() -> None:
    decision = Decision("deny", "demo", 1, "max_cost_per_day", Decimal("1.00"), Decimal("1.50"))
    exc = PolicyDenied(decision)
    assert exc.decision is decision


def test_policy_denied_is_exception_not_valueerror() -> None:
    decision = Decision("deny", "demo", 1, "max_cost_per_day", Decimal("1.00"), Decimal("1.50"))
    exc = PolicyDenied(decision)
    assert not isinstance(exc, ValueError)
    assert isinstance(exc, Exception)


def test_policy_denied_str_names_the_rule() -> None:
    decision = Decision("deny", "demo", 1, "max_cost_per_day", Decimal("1.00"), Decimal("1.50"))
    message = str(PolicyDenied(decision))
    for needle in ("max_cost_per_day", "1.00", "1.50"):
        assert needle in message, f"PolicyDenied message missing {needle!r}: {message}"
