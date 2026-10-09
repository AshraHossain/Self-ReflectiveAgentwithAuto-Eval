---
phase: 03-policy-engine-budget-ledger-mock-llm
plan: 03
subsystem: testing
tags: [mock-llm, scripted-client, budget-enforcement, end-to-end-proof]

# Dependency graph
requires:
  - phase: 03-policy-engine-budget-ledger-mock-llm (plan 01)
    provides: "eacp.engine: pure decide(), Decision, BudgetState, Usage, LlmCall, ToolCall, cost_of()"
  - phase: 03-policy-engine-budget-ledger-mock-llm (plan 02)
    provides: "eacp.ledger.SQLiteBudgetLedger: admit(run_id, call_key, policy, request)/reconcile(admission, usage) under BEGIN IMMEDIATE"
provides:
  - "eacp.mock_llm.MockLLM/MockTurn/MockToolCall: framework-free scripted LLM, no network, no provider API key, non-zero usage default, loop=True runaway mode"
  - "End-to-end proof that decide() -> SQLiteBudgetLedger -> a scripted client actually stops a runaway loop BEFORE the budget-breaking call, by exact mock.calls count"
affects: [phase-04-audit-log, phase-05-07-adapters]

actuals:
  tokens: 2721
  tasks: 2
  commits: 2
  plan_head_before: 04c5885e3c1d327679b73e6244f400a7f0874d43
  plan_head_after: 63295ff0c3a034f0975b7da9060f2712cb601508

tech-stack:
  added: []
  patterns:
    - "MockTurn's usage field defaults to Usage(40, 12, \"provider\") -- a non-zero dataclass default, so a caller who scripts a turn without thinking about usage at all still exercises real budget arithmetic instead of silently zeroing it"
    - "MockLLM.complete() never lets StopIteration escape -- script exhaustion (non-looping) raises RuntimeError naming the call count served, distinguishing test-harness misuse from a Python bug"
    - "itertools.cycle(script) for loop=True runaway mode -- one line, no custom generator class"
    - "End-to-end budget proofs assert an exact, COMPUTED mock.calls count (e.g. int(policy.max_cost_per_day // cost_of(...))), never a hardcoded literal -- a hardcoded number could pass even if the block fired one call too late"

key-files:
  created:
    - src/eacp/mock_llm.py
    - tests/test_mock_llm.py
  modified: []

key-decisions:
  - "test_mock_is_keyless drives the SAME full admit()/complete()/reconcile() scenario as the tracer proof (not a bare MockLLM call) with both provider API-key env vars deleted, so success criterion 4 is proven against the whole governed path, not just MockLLM.complete() in isolation"
  - "The forbidden-tool test calls ledger.admit(ToolCall(...)) directly rather than routing through MockLLM.complete() first, per the plan's explicit intent: the restriction must be proven to live in the governance layer (admit()), not in the mock declining to script a call -- MockLLM has no tool-restriction logic of its own, by design"
  - "No changes needed to mock_llm.py in Task 2 -- the already-built MockLLM (loop=True, non-zero default usage, calls counter) was sufficient for all four BUDGET-01/04/05 end-to-end proofs with no gap"

requirements-completed: [BUDGET-01, BUDGET-04, BUDGET-05]

coverage:
  - id: D1
    description: "MockLLM emits scripted turns (text and tool calls) in exact script order, each carrying non-zero provider usage by default, with no network call and no provider API key present"
    requirement: "BUDGET-05"
    verification:
      - kind: unit
        ref: "tests/test_mock_llm.py#test_mock_emits_scripted_turns_in_order_with_nonzero_usage"
        status: pass
      - kind: unit
        ref: "tests/test_mock_llm.py#test_mock_is_keyless"
        status: pass
    human_judgment: false
  - id: D2
    description: "Script exhaustion on a non-looping MockLLM raises RuntimeError naming the call count served, never leaking StopIteration"
    verification:
      - kind: unit
        ref: "tests/test_mock_llm.py#test_mock_script_exhaustion_raises"
        status: pass
    human_judgment: false
  - id: D3
    description: "A real SQLiteBudgetLedger admits and reconciles the mock's scripted turns end to end, with recorded spend/tokens reflecting the SCRIPTED usage (deliberately different from the pre-call estimate), not the estimate"
    verification:
      - kind: integration
        ref: "tests/test_mock_llm.py#test_mock_turns_flow_through_a_real_ledger"
        status: pass
    human_judgment: false
  - id: D4
    description: "A runaway loop=True mock is stopped by max_cost_per_day at the exact call the policy's price and scripted usage predict, proven by a computed (not hardcoded) mock.calls assertion -- the governance chain blocks BEFORE the call that would break the budget, not after"
    requirement: "BUDGET-01"
    verification:
      - kind: integration
        ref: "tests/test_mock_llm.py#test_runaway_mock_is_stopped_before_the_blocking_call"
        status: pass
    human_judgment: false
  - id: D5
    description: "The same runaway loop shape is stopped by max_steps at exactly policy.max_steps calls, independent of enormous token/cost headroom"
    requirement: "BUDGET-04"
    verification:
      - kind: integration
        ref: "tests/test_mock_llm.py#test_runaway_mock_is_stopped_by_max_steps_independent_of_budget"
        status: pass
    human_judgment: false
  - id: D6
    description: "A forbidden tool call is denied by ledger.admit(ToolCall(...)) before the mock is ever invoked for that step -- the restriction is enforced by the governance layer, not by the mock declining to script it"
    verification:
      - kind: unit
        ref: "tests/test_mock_llm.py#test_forbidden_tool_call_is_denied_before_the_mock_is_invoked"
        status: pass
    human_judgment: false
  - id: D7
    description: "A scripted MISSING usage turn reconciles to the pre-call estimate, not zero, and increments the run's missing_usage counter"
    requirement: "BUDGET-05"
    verification:
      - kind: unit
        ref: "tests/test_mock_llm.py#test_missing_usage_turn_does_not_zero_the_spend"
        status: pass
    human_judgment: false

duration: 30min
completed: 2026-10-09
status: complete
---

# Phase 3 Plan 03: Mock LLM & End-to-End Budget Proof Summary

**`MockLLM` is a framework-free, keyless, scripted client proven to drive the full `decide()` -> `SQLiteBudgetLedger` -> client chain, stopping a runaway loop by exact, computed call count before the budget-breaking call ever executes.**

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-10-09
- **Tasks:** 2
- **Files modified:** 2 (both created)

## Accomplishments
- `src/eacp/mock_llm.py`: `MockLLM`/`MockTurn`/`MockToolCall` -- stdlib + `eacp.engine.Usage` only, no agent framework, no `os` import at all (not "happens to work without a key," but "never reads one")
- `MockTurn.usage` defaults to `Usage(40, 12, "provider")`: a caller who scripts a turn without thinking about usage still exercises real, non-zero budget arithmetic
- `loop=True` repeats the script forever via `itertools.cycle`; script exhaustion (non-looping) raises `RuntimeError` naming the call count served, never `StopIteration`
- Tracer proof (`test_mock_turns_flow_through_a_real_ledger`): a real `SQLiteBudgetLedger` admits and reconciles scripted usage end to end, with recorded spend/tokens reflecting the scripted values (deliberately different from the pre-call estimate), not the estimate
- `test_mock_is_keyless` drives that same full scenario with `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` deliberately deleted via `monkeypatch.delenv`
- BUDGET-01 end-to-end proof: a `loop=True` mock scripted with fixed non-zero usage is denied by `max_cost_per_day` at exactly the call count computed from the policy's price and the scripted usage (`int(policy.max_cost_per_day // cost_of(...))`) -- never a hardcoded literal, so the test cannot pass if the block fires one call too late
- BUDGET-04 end-to-end proof: the same loop shape is independently stopped by `max_steps` at exactly `policy.max_steps` calls, with token/cost limits set enormous
- Forbidden-tool proof: `ledger.admit(ToolCall(...))` denies directly, before the mock is ever invoked for that step (`mock.calls == 0`)
- BUDGET-05 proof: a `MISSING` usage turn reconciles to the pre-call estimate (not zero) and increments `missing_usage`
- Full suite (Phase 1+2+3): **125 passed** (117 baseline + 8 new in `tests/test_mock_llm.py`); `mypy --strict` (24 source files), ruff, and `uv lock --check` all clean
- This was the last plan in the phase -- Phase 3 now moves to code review, verification, and security audit

## Task Commits

Each task was committed atomically:

1. **Task 1: MockLLM core, wired end-to-end through the real ledger** - `8ac5289` (feat)
2. **Task 2: Runaway loop stopped by budget and by max_steps; forbidden tool and MISSING usage** - `63295ff` (test)

**Plan metadata:** committed separately with this SUMMARY.

## Files Created/Modified
- `src/eacp/mock_llm.py` - New: `MockToolCall`, `MockTurn` (non-zero default usage), `MockLLM` (scripted/looping, `.complete()`, `.calls`)
- `tests/test_mock_llm.py` - New: success criterion 4 (scripted order, non-zero usage, exhaustion, keyless) plus the BUDGET-01/04/05 end-to-end integration proofs against a real `SQLiteBudgetLedger`

## Decisions Made
- `test_mock_is_keyless` runs the full admit/complete/reconcile scenario (not a bare `MockLLM.complete()` call) with both provider API-key env vars unset, so the keylessness claim is proven against the whole governed path
- The forbidden-tool test calls `ledger.admit(ToolCall(...))` directly rather than routing through `MockLLM.complete()` first -- the plan is explicit that this proves the restriction lives in the governance layer, not in the mock declining to script a call it was never asked to refuse
- No changes to `mock_llm.py` were needed in Task 2; the Task 1 `MockLLM` (loop mode, non-zero default usage, `.calls` counter) was sufficient for all four end-to-end proofs with no gap, so no `reset()` method or other addition was added

## Deviations from Plan

None - plan executed exactly as written. The worktree required a `git merge --ff-only main` (it was behind main's tip, carrying Plan 03-01/03-02's already-committed history) and a `VIRTUAL_ENV= uv sync` per the known environment bug note, both done before any code was written and verified against the known-environment-bug/known-worktree-staleness-pattern guidance in the dispatch objective -- neither constitutes a deviation from the plan's own task content.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 3 is complete: `engine.py` (Plan 03-01), `ledger.py` (Plan 03-02), and `mock_llm.py` (Plan 03-03) together prove the whole governance chain end to end
- Phase 4 (audit log) can build directly on `Decision`/`Admission`/`PolicyDenied`; `Decision`'s `Decimal`-typed fields still need `str()` rendering before `json.dumps` (G-3, documented in `engine.py`, not built here)
- Phases 5-7's adapters wrap `MockLLM` per-framework (`FakeMessagesListChatModel` for LangGraph, a `crewai.llms.base_llm.BaseLLM` subclass for CrewAI, `ag2.testing.TestConfig` for ag2) rather than rebuilding scripted-client logic
- No blockers. Ready for `/gsd-verify-work` and the phase's code review / security audit gate

---
*Phase: 03-policy-engine-budget-ledger-mock-llm*
*Completed: 2026-10-09*

## Self-Check: PASSED

- FOUND: src/eacp/mock_llm.py
- FOUND: tests/test_mock_llm.py
- FOUND: 8ac5289 (Task 1 commit)
- FOUND: 63295ff (Task 2 commit)
