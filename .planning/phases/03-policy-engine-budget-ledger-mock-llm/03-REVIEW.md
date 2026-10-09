---
phase: 03-policy-engine-budget-ledger-mock-llm
reviewed: 2026-10-09T22:50:22Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - src/eacp/policy.py
  - src/eacp/errors.py
  - src/eacp/engine.py
  - src/eacp/ledger.py
  - src/eacp/mock_llm.py
  - tests/conftest.py
  - tests/test_policy.py
  - tests/test_engine.py
  - tests/test_ledger.py
  - tests/test_mock_llm.py
findings:
  critical: 1
  warning: 3
  info: 1
  total: 5
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-10-09T22:50:22Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Reviewed the pure decision core (`engine.py`), the SQLite budget ledger (`ledger.py`), the
scripted mock LLM (`mock_llm.py`), and the `policy.py`/`errors.py` extensions, plus their
test files. The three SUMMARYs' self-reported design (`isolation_level=None` + `BEGIN
IMMEDIATE`, `ROUND_CEILING` cost quantization, the MISSING-vs-zero `Usage` trichotomy, no
SQL string interpolation, no forbidden-framework imports) all check out under direct
reading and two live reproductions run against the actual installed package.

One finding is a genuine, reproduced BLOCKER: the exact "real cost silently rounds to
zero" failure mode that `engine.cost_of`'s `ROUND_CEILING` was built specifically to
prevent (documented as Pitfall 2 / T-03-02 in the plan's own threat model) still reaches
production through a path the plan didn't cover — `ModelPrice`'s own field validator,
which quantizes a per-token price with the *default* rounding mode, not `ROUND_CEILING`.
A model priced low enough rounds to an exact `$0.000000` per token, after which no volume
of calls against that model can ever trip `max_cost_per_day`. Reproduced directly against
the installed code (see finding for the exact commands and output).

Three further WARNINGs cover a ledger misuse path that crashes with an opaque `TypeError`
instead of a clear error, a replay-idempotency path that doesn't validate request
consistency on a `call_key` collision, and a replayed `Decision`'s `observed` field
reporting the wrong quantity (a correctness gap for the Phase 4 audit consumer the current
SUMMARYs explicitly say will read `Decision` directly). One INFO item flags dead logic in
a test assertion.

No SQL injection, no float arithmetic in the money path, no forbidden-framework import at
any nesting depth, and no `isolation_level` other than `None` were found anywhere in the
reviewed files — those specific asks in the review brief check out clean.

## Critical Issues

### CR-01: `ModelPrice` quantizes a per-token price with the wrong rounding mode — a tiny nonzero price silently becomes exactly `$0`, bypassing budget enforcement entirely for that model

**File:** `src/eacp/policy.py:75-80` (`_quantize_cost`) and `:94-97` (`ModelPrice._quantize`)

**Issue:** `engine.cost_of` (src/eacp/engine.py:78-82) deliberately quantizes a computed
*cost* with `ROUND_CEILING` specifically because the Decimal default (`ROUND_HALF_EVEN`)
can round a real, nonzero cost down to `0.000000` (this is Pitfall 2 / T-03-02 in the
plan's own threat model, and the review brief for this phase explicitly asked to check for
a surviving zero-cost false negative). That fix was applied only to the *per-call cost
computation*, not to the *price itself*. `ModelPrice.input_per_mtok`/`output_per_mtok`
(and `Policy.max_cost_per_day`) are quantized through the shared `_quantize_cost` helper,
which calls `v.quantize(COST_EXP)` with no rounding argument — the Decimal default,
`ROUND_HALF_EVEN`. A policy author who specifies a per-Mtok price smaller than
`$0.0000005` (plausible for a very cheap/local model, or simply a typo dropping a decimal
place) gets a `ModelPrice` that is stored as literally `Decimal("0.000000")`. From that
point on, `cost_of` for that model computes `raw = 0` exactly for any volume of tokens —
not a rounding artifact, the *informed* price is zero — so `decide()`'s
`spend <= policy.max_cost_per_day` check can never deny on cost for that model, no matter
how many calls run. This is a complete, silent bypass of `max_cost_per_day` for any model
priced below the rounding threshold, i.e. exactly the "absence/zero is never unlimited"
guarantee (D-08/D-12, OD-2) failing for a path the plan's Pitfall-2 fix didn't reach.

Reproduced directly against the installed package:

```
$ uv run --no-sync python -c "
from decimal import Decimal
from eacp.policy import ModelPrice
from eacp.engine import cost_of
p = ModelPrice(input_per_mtok=Decimal('0.0000003'), output_per_mtok=Decimal(0))
print('stored input_per_mtok:', p.input_per_mtok)
print('cost for 10,000,000 tokens:', cost_of(p, input_tokens=10_000_000, output_tokens=0))
"
stored input_per_mtok: 0.000000
cost for 10,000,000 tokens: 0.000000
```

10 million tokens against a validated, non-zero-intent price produces a recorded cost of
exactly `$0.000000` — `max_cost_per_day` is unenforceable for this model at any scale.

**Fix:** Quantize `ModelPrice`'s two fields with `ROUND_CEILING` (consistent with
`cost_of`'s own reasoning: a price should never be allowed to round away real intended
cost), or at minimum reject the silent-zero case explicitly:

```python
from decimal import ROUND_CEILING

def _quantize_cost(v: Decimal, *, rounding: str = ROUND_CEILING) -> Decimal:
    try:
        return v.quantize(COST_EXP, rounding=rounding)
    except InvalidOperation:
        raise ValueError("cost is out of range") from None

class ModelPrice(BaseModel):
    ...
    @field_validator("input_per_mtok", "output_per_mtok")
    @classmethod
    def _quantize(cls, v: Decimal) -> Decimal:
        q = _quantize_cost(v)
        if v != 0 and q == 0:
            raise ValueError("price rounds to zero at 6 decimal places; use 0 explicitly for a free model")
        return q
```

(`Policy.max_cost_per_day` can keep the current default-rounding `_quantize_cost` call
unchanged — rounding a *limit* slightly either way is a minor precision question, not a
bypass; only the price fields create the zero-cost loophole.)

## Warnings

### WR-01: `ledger.reconcile()` crashes with an opaque `TypeError` if called with non-`MISSING` usage against a `ToolCall`-derived `Admission`

**File:** `src/eacp/ledger.py:325-334`

**Issue:** A `ToolCall` reservation stores `price_input_per_mtok`/`price_output_per_mtok`
as `NULL` (src/eacp/ledger.py:71-73, :232), since nothing is estimated for a tool call. If
`reconcile()` is ever called on such an `Admission` with a non-`"MISSING"` `Usage` (a
plausible caller mistake — e.g. an adapter that always calls `admit → execute →
reconcile` without special-casing tool calls), the code falls into the `else` branch and
does `Decimal(row["price_input_per_mtok"])` on a `None` value:

```
$ uv run --no-sync python -c "
...
admission = ledger.admit('run1', '0', policy, ToolCall('search'))
ledger.reconcile(admission, Usage(5, 5, 'provider'))
"
raised: TypeError conversion from NoneType to Decimal is not supported
```

The resulting `TypeError` gives no indication that the real problem is "this admission was
never meant to be reconciled" — it looks like an internal driver bug, not a caller misuse.

**Fix:** Guard explicitly and raise something actionable:

```python
if row["price_input_per_mtok"] is None and usage.usage_source != "MISSING":
    raise ValueError(
        "cannot reconcile a tool-call reservation with non-MISSING usage "
        f"(run_id={admission.run_id!r}, call_key={admission.call_key!r})"
    )
```

### WR-02: Replay short-circuit in `admit()` doesn't validate that the replayed request matches what was originally admitted

**File:** `src/eacp/ledger.py:185-200`

**Issue:** G-1's idempotency design is correct in spirit — an existing `(run_id,
call_key)` row short-circuits `admit()` without re-running `decide()` or charging again.
But nothing checks that the `request` passed on replay (model, tool name, token count)
matches what was originally admitted under that `call_key`. If a caller bug reuses a
`call_key` for a semantically different request (e.g. an off-by-one in step numbering, or
a retried call with different input), `admit()` silently returns the stale original
`Admission` with no signal that anything is wrong — the caller proceeds believing the
*new* request was admitted, while the ledger's bookkeeping still reflects only the *old*
one.

**Fix:** At minimum, assert/log when the replayed row's stored `tokens`/`cost` disagree
with what `decide()` would compute fresh for the current `request` (a cheap sanity check,
not a full re-run), so a `call_key` collision across different requests surfaces instead
of silently returning mismatched data.

### WR-03: A replayed `Decision`'s `observed` field reports the wrong quantity for `max_cost_per_day`, risking a misleading audit trail

**File:** `src/eacp/ledger.py:99-121` (`_replay_decision`)

**Issue:** On a genuine `decide()` call, `Decision.observed` for the `max_cost_per_day`
rule is the *cumulative projected daily spend* (`state.spent_today + cost_of(...)`,
src/eacp/engine.py:121-122). On a replay, `_replay_decision` instead sets
`observed=Decimal(row["cost"])` — the cost of *this single reservation*, not the
cumulative daily total. These are different numbers whenever any other call happened the
same day. The 03-02-SUMMARY.md documents this as a deliberate simplification ("only
budget/step state... is load-bearing for G-1"), but Phase 3's own SUMMARYs also state
"Phase 4's audit log can read `Admission`/`Decision` directly" — a future reader who
trusts `Admission.decision.observed` as "the daily spend this call was admitted against"
will get a wrong value whenever the admission was served from the replay path.

**Fix:** Either persist the real `observed`/`limit` from the original decision (a small,
already-precedented schema addition, the same move made for the price columns), or make
the synthetic nature impossible to miss — e.g. a distinct `rule` value or sentinel
(`observed=None`/a dedicated `is_replay: bool` on `Admission`) rather than a
plausible-looking but wrong number under the real rule name.

## Info

### IN-01: Dead branch in a test assertion

**File:** `tests/test_engine.py:56`

**Issue:** `assert decision.limit is not None or decision.limit == 0` — the second clause
can never change the outcome: if `limit` actually were `None`, `None == 0` is also
`False`, so the `or` adds nothing and the assertion behaves identically to
`assert decision.limit is not None`. The `== 0` clause reads as if it were handling a
"zero is falsy but valid" case, but no such case can reach this line (there's no boolean
coercion involved), so it's misleading dead logic.

**Fix:** `assert decision.limit is not None, decision`.

---

_Reviewed: 2026-10-09T22:50:22Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
