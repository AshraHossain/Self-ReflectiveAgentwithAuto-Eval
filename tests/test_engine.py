"""POLICY-03 and BUDGET-05's executable contract for the pure decision core."""

from collections.abc import Callable
from decimal import Decimal

from eacp.engine import BudgetState, Decision, LlmCall, ToolCall, decide
from eacp.policy import Policy, load_yaml_mapping

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
