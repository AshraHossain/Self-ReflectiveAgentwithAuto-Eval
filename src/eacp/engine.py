"""Pure policy decision core (POLICY-03): ``decide()`` and the types around it.

No I/O, no clock, no agent framework import at any nesting depth -- enforced by the
import allowlist below and re-checked at both the AST and module-scope-import level by
this plan's verify step. The clock and all persistence live in Plan 03-02's ledger, which
calls ``decide()`` from inside its own transaction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from typing import Literal

from eacp.policy import COST_EXP, ModelPrice, Policy

# "provider" = a real adapter/mock reading; "estimated" = this plan's own pre-call guess;
# "MISSING" = no reading arrived at all. Never conflate the third with a zero reading.
UsageSource = Literal["provider", "estimated", "MISSING"]

# Rule names are exactly the Policy field names that decided the outcome, so Phase 4's
# audit log needs no separate mapping table from rule to policy field.
Rule = Literal[
    "max_steps", "forbidden_tools", "allowed_tools",
    "model_prices", "max_tokens_per_run", "max_cost_per_day",
]

Observed = int | Decimal | str
Limit = int | Decimal | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Decision:
    """The only channel through which decide() communicates allow/deny (POLICY-03).

    G-3 (Phase 4 warning): ``dataclasses.asdict(decision)`` followed by stdlib
    ``json.dumps`` raises ``TypeError`` on the ``Decimal``-typed ``limit``/``observed``
    fields -- ``json`` has no native ``Decimal`` encoder. Render those two fields with
    ``str()`` before serializing. This is documentation only; no serialization helper is
    built in this plan.
    """

    outcome: Literal["allow", "deny"]  # Phase 4 adds "require_approval"; additive widening
    policy_id: str
    version: int
    rule: Rule
    limit: Limit
    observed: Observed


@dataclass(frozen=True, slots=True)
class LlmCall:
    model: str
    input_tokens: int  # caller's estimate (estimate_tokens) or a better count
    max_output_tokens: int | None


@dataclass(frozen=True, slots=True)
class ToolCall:
    tool_name: str


@dataclass(frozen=True, slots=True)
class BudgetState:
    steps_taken: int
    run_tokens: int
    spent_today: Decimal


def estimate_tokens(text: str) -> int:
    # ponytail: chars/4 heuristic, no tiktoken in core (not in the dependency lock).
    # Underestimates code/CJK; the error is bounded to one call by reconciliation.
    # Upgrade: adapters pass a real tokenizer count through LlmCall.input_tokens.
    return math.ceil(len(text) / 4)


def cost_of(price: ModelPrice, input_tokens: int, output_tokens: int) -> Decimal:
    raw = (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / 1_000_000
    # ROUND_CEILING, never the default ROUND_HALF_EVEN: a real 1-token cost at $0.10/Mtok
    # quantizes to 0.000000 under the default, silently hiding real spend (Pitfall 2).
    return raw.quantize(COST_EXP, rounding=ROUND_CEILING)


def output_estimate(policy: Policy, req: LlmCall, state: BudgetState) -> int:
    # A5: with no caller ceiling, the reservation fills the run's remaining token headroom,
    # not zero and not unbounded. Overshoot against the real output is bounded to one call.
    remaining = max(policy.max_tokens_per_run - state.run_tokens - req.input_tokens, 0)
    return remaining if req.max_output_tokens is None else min(req.max_output_tokens, remaining)


def decide(policy: Policy, request: LlmCall | ToolCall, state: BudgetState) -> Decision:
    def mk(ok: bool, rule: Rule, limit: Limit, observed: Observed) -> Decision:
        return Decision(
            "allow" if ok else "deny", policy.policy_id, policy.version, rule, limit, observed
        )

    # BUDGET-04: max_steps is checked first and independently of token/cost accounting --
    # a runaway loop stops even with enormous token/cost headroom.
    steps = state.steps_taken + 1
    if steps > policy.max_steps:
        return mk(False, "max_steps", policy.max_steps, steps)

    if isinstance(request, ToolCall):
        name = request.tool_name
        # forbidden_tools wins ties and is checked first (OD-3).
        if name in policy.forbidden_tools:
            return mk(False, "forbidden_tools", tuple(policy.forbidden_tools), name)
        # OD-3: [] allows nothing -- `in` on an empty list is always False.
        return mk(name in policy.allowed_tools, "allowed_tools", tuple(policy.allowed_tools), name)

    price = policy.model_prices.get(request.model)
    if price is None:  # OD-2: unpriced model fail-closes before any cost arithmetic runs
        return mk(False, "model_prices", tuple(sorted(policy.model_prices)), request.model)

    out = output_estimate(policy, request, state)
    tokens = state.run_tokens + request.input_tokens + out
    if tokens > policy.max_tokens_per_run:
        return mk(False, "max_tokens_per_run", policy.max_tokens_per_run, tokens)

    spend = state.spent_today + cost_of(price, request.input_tokens, out)
    return mk(spend <= policy.max_cost_per_day, "max_cost_per_day", policy.max_cost_per_day, spend)


@dataclass(frozen=True, slots=True)
class Usage:
    """A usage reading that can never confuse "no reading" with "a zero reading".

    ``usage_source == "MISSING"`` if and only if both token counts are ``None``. Any other
    source requires both counts present, non-negative, and not ``bool`` (``bool`` is an
    ``int`` subclass in Python, so a stray ``True``/``False`` must be rejected explicitly).
    """

    input_tokens: int | None
    output_tokens: int | None
    usage_source: UsageSource

    def __post_init__(self) -> None:
        missing = self.usage_source == "MISSING"
        for n in (self.input_tokens, self.output_tokens):
            if (n is None) is not missing:
                raise ValueError(
                    "MISSING usage carries no counts; any other source requires both"
                )
            if n is not None and (isinstance(n, bool) or n < 0):
                raise ValueError("token counts must be non-negative ints, not bool")
