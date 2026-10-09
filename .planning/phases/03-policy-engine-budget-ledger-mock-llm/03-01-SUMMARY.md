---
phase: 03-policy-engine-budget-ledger-mock-llm
plan: 01
subsystem: policy-engine
tags: [pydantic, decimal, pure-function, policy-engine, budget]

# Dependency graph
requires:
  - phase: 02-core-schema-registry-stores
    provides: Policy/policy_hash/load_policy_file trust boundary this plan extends
provides:
  - "Policy.max_steps and Policy.model_prices as required content fields (OD-1, OD-2)"
  - "eacp.engine: pure decide(), Decision, LlmCall, ToolCall, BudgetState, Usage, estimate_tokens(), cost_of(), output_estimate()"
  - "eacp.errors.PolicyDenied carrying a Decision"
affects: [03-02-budget-ledger, 03-03-mock-llm, phase-04-audit-log]

actuals:
  tokens: 5876
  tasks: 3
  commits: 3
  plan_head_before: 15cf71ab575adfda06fc22d71021b36206bfda26
  plan_head_after: 359a68eb49ac61c6ee12a98f75c58e581e31fcf6

tech-stack:
  added: []
  patterns:
    - "Pure decision core: eacp.engine imports only stdlib + eacp.policy, enforced by an AST-walk test and a module-scope sys.modules leak check"
    - "ROUND_CEILING money quantization (never the Decimal default ROUND_HALF_EVEN) so a real cost never silently rounds to zero"
    - "TYPE_CHECKING-only cross-module import to break an errors -> engine -> policy -> errors cycle"
    - "Usage trichotomy: MISSING carries no counts, every other source requires both, non-negative, non-bool"

key-files:
  created:
    - src/eacp/engine.py
    - tests/test_engine.py
  modified:
    - src/eacp/policy.py
    - src/eacp/errors.py
    - tests/conftest.py
    - tests/test_policy.py

key-decisions:
  - "Renamed _COST_EXP to public COST_EXP and extracted a shared _quantize_cost() helper so Policy.max_cost_per_day and ModelPrice's two fields share one InvalidOperation handler instead of three copies"
  - "_ModelName widened from _PolicyId's charset with ':' and '/' so names like ollama/llama3.1 validate as a dict key"
  - "Numeric boundary tests (Task 2) construct BudgetState directly rather than round-tripping through a YAML policy_yaml fixture per boundary point, per the plan's own guidance"
  - "PolicyDenied subclasses Exception (not ValueError) so a caller can catch a governance halt separately from a bad-value bug; Decision is imported under TYPE_CHECKING only"

requirements-completed: [POLICY-03, BUDGET-05]

coverage:
  - id: D1
    description: "Policy schema extended with required max_steps and model_prices fields; policy_hash stays stable across their formatting and the pinned nine-field key set is enforced in the same commit as the schema change (Pitfall 6)"
    requirement: "POLICY-03"
    verification:
      - kind: unit
        ref: "tests/test_policy.py#test_hash_is_content_addressed"
        status: pass
      - kind: unit
        ref: "tests/test_policy.py#test_hashed_key_set_is_pinned"
        status: pass
      - kind: unit
        ref: "tests/test_policy.py#test_every_limit_field_is_required[max_steps]"
        status: pass
      - kind: unit
        ref: "tests/test_policy.py#test_every_limit_field_is_required[model_prices]"
        status: pass
    human_judgment: false
  - id: D2
    description: "eacp.engine.decide() is a pure function (no I/O, no clock, no framework import at any nesting depth) returning a structured Decision -- never a bare boolean -- for an allowed and a denied case of both LlmCall and ToolCall"
    requirement: "POLICY-03"
    verification:
      - kind: unit
        ref: "tests/test_engine.py#test_decide_returns_a_structured_decision"
        status: pass
      - kind: unit
        ref: "tests/test_engine.py#test_engine_imports_are_pure"
        status: pass
      - kind: unit
        ref: "tests/test_engine.py#test_numeric_deny_iff_observed_exceeds_limit"
        status: pass
      - kind: unit
        ref: "tests/test_engine.py#test_forbidden_tools_beats_allowed_tools"
        status: pass
      - kind: unit
        ref: "tests/test_engine.py#test_empty_allowed_tools_denies_every_tool"
        status: pass
      - kind: unit
        ref: "tests/test_engine.py#test_unpriced_model_is_denied"
        status: pass
      - kind: unit
        ref: "tests/test_engine.py#test_max_steps_is_checked_before_tokens_or_cost"
        status: pass
    human_judgment: false
  - id: D3
    description: "Usage readings are either MISSING with no counts or a source with both counts present, non-negative, non-bool; cost_of always rounds a real cost up (ROUND_CEILING), never to zero"
    requirement: "BUDGET-05"
    verification:
      - kind: unit
        ref: "tests/test_engine.py#test_usage_missing_requires_no_counts"
        status: pass
      - kind: unit
        ref: "tests/test_engine.py#test_usage_provider_requires_both_counts"
        status: pass
      - kind: unit
        ref: "tests/test_engine.py#test_usage_rejects_negative_counts"
        status: pass
      - kind: unit
        ref: "tests/test_engine.py#test_usage_rejects_bool_counts"
        status: pass
      - kind: unit
        ref: "direct behavioral check in 03-01-PLAN.md Task 1 verify (cost_of 1 token @ $0.10/Mtok == Decimal('0.000001'))"
        status: pass
    human_judgment: false
  - id: D4
    description: "PolicyDenied carries a Decision, subclasses Exception (not ValueError), and has no runtime dependency on eacp.engine"
    verification:
      - kind: unit
        ref: "tests/test_engine.py#test_policy_denied_carries_the_decision"
        status: pass
      - kind: unit
        ref: "tests/test_engine.py#test_policy_denied_is_exception_not_valueerror"
        status: pass
      - kind: unit
        ref: "tests/test_engine.py#test_policy_denied_str_names_the_rule"
        status: pass
    human_judgment: false

duration: 35min
completed: 2026-10-09
status: complete
---

# Phase 3 Plan 01: Policy Schema Extension & Pure decide() Engine Summary

**`Policy` gained required `max_steps`/`model_prices` fields and a new pure `eacp.engine.decide()` turns a policy, request, and budget state into a structured `Decision` with `ROUND_CEILING` money arithmetic and a MISSING-vs-zero-safe `Usage` type.**

## Performance

- **Duration:** 35 min (resumed session -- see Issues Encountered)
- **Completed:** 2026-10-09
- **Tasks:** 3
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments
- `Policy` now requires `max_steps` (OD-1) and `model_prices: dict[_ModelName, ModelPrice]` (OD-2) as content fields; `policy_hash` stays format-stable and the pinned key set now names all nine enforceable fields
- `eacp/engine.py` built from scratch: `Decision`, `LlmCall`, `ToolCall`, `BudgetState`, `Usage`, `decide()`, `estimate_tokens()`, `cost_of()`, `output_estimate()` -- imports only the stdlib allowlist plus `eacp.policy`, verified by both an AST-walk test and a `sys.modules` leak check
- `decide()`'s full rule order implemented and exhaustively tested: `max_steps` first and independent of token/cost headroom (BUDGET-04), then tool branch (`forbidden_tools` beats `allowed_tools`, empty allowlist denies all), then LLM branch (unpriced model fail-closes with rule `model_prices`, then `max_tokens_per_run`, then `max_cost_per_day`)
- `cost_of()` quantizes with `ROUND_CEILING` -- a real 1-token cost at $0.10/Mtok rounds to `Decimal("0.000001")`, never to zero (Pitfall 2)
- `Usage.__post_init__` enforces the MISSING-vs-zero trichotomy: `MISSING` carries no counts, every other source requires both counts present, non-negative, non-bool
- `PolicyDenied(Exception)` added to `errors.py`, carrying a `Decision`, with `Decision` imported under `TYPE_CHECKING` only to avoid an `errors -> engine -> policy -> errors` cycle

## Task Commits

Each task was committed atomically:

1. **Task 1: Policy schema extension + decide() wired end-to-end** - `7474d8e` (feat)
2. **Task 2: Exhaustive decide() correctness** - `a03eaf4` (test)
3. **Task 3: PolicyDenied exception** - `359a68e` (feat)

**Plan metadata:** committed separately with this SUMMARY.

## Files Created/Modified
- `src/eacp/engine.py` - New pure decision core: Decision/LlmCall/ToolCall/BudgetState/Usage, decide(), estimate_tokens(), cost_of(), output_estimate()
- `tests/test_engine.py` - POLICY-03/BUDGET-05 executable contract: tracer proof + exhaustive boundary/semantic tests + PolicyDenied tests
- `src/eacp/policy.py` - Added ModelPrice, _ModelName, Policy.max_steps/model_prices; renamed _COST_EXP to public COST_EXP; extracted _quantize_cost() helper
- `src/eacp/errors.py` - Added PolicyDenied(Exception) carrying a Decision
- `tests/conftest.py` - _VALID_POLICY fixture extended with max_steps and model_prices
- `tests/test_policy.py` - Five Pitfall-6 sites updated: ALL_FIELDS, _HASH_A/_HASH_B (with model_prices format variation), hash-changes parametrize table, pinned key set

## Decisions Made
- Renamed `_COST_EXP` to public `COST_EXP` and extracted `_quantize_cost()` so `Policy.max_cost_per_day` and `ModelPrice`'s two fields share one `InvalidOperation` handler rather than three copies
- `_ModelName` widened from `_PolicyId`'s charset with `:` and `/` so names like `ollama/llama3.1` validate as a `model_prices` dict key
- Task 2's numeric boundary test builds `BudgetState` directly (not via a YAML round-trip per case) and sets up each rule's observed value precisely by zeroing out the other two dimensions (zero-token, zero-output-ceiling `LlmCall`) -- this keeps the parametrized test's arithmetic exact and auditable
- `test_hash_stability_survives_the_schema_change` was folded into the existing `test_hash_is_content_addressed` (its docstring now explains the dual purpose) rather than added as a near-duplicate function, per the plan's own stated preference

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Worktree venv was not synced; shell's inherited `VIRTUAL_ENV` silently redirected all verification to the main repo's code**
- **Found during:** Task 1, first `uv run --no-sync pytest` after writing `engine.py`
- **Issue:** The worktree's own `.venv` existed but had never been `uv sync`'d (only created, never populated with the `eacp` project itself). Separately, the invoking shell's profile exports `VIRTUAL_ENV` pointing at the **main repo's** `.venv`. `uv run --no-sync` prints a warning that this mismatched `VIRTUAL_ENV` "will be ignored," but in practice the spawned Python process still inherited it (`sys.prefix` == main repo `.venv`, `sys.executable` == main repo's `python`), and `eacp` resolved to the main repo's `src/eacp` (an old editable install there) rather than the worktree's own `src/eacp`. Net effect: every `uv run` command in this plan would have silently verified against the WRONG code (the main repo's unmodified Phase 2 files) while reporting false negatives/positives that looked like real test failures, which is exactly how the schema-change tests briefly "failed" with stale-schema errors.
- **Fix:** Confirmed the bug with a diagnostic probe test (`sys.prefix`, `sys.executable`, `sys.path`), then ran every subsequent `uv` command with `VIRTUAL_ENV=` (forcibly cleared) prefixed, and ran `VIRTUAL_ENV= uv sync` once to install `eacp` and its dev dependencies into the worktree's own `.venv`. All verification in this SUMMARY was re-run after this fix and reflects the worktree's actual code.
- **Files modified:** none (environment-only; no source files affected). The diagnostic probe test file was deleted before committing.
- **Verification:** `VIRTUAL_ENV= uv run --no-sync python -c "import sys; print(sys.prefix)"` now prints the worktree's own `.venv` path; full suite reruns under the corrected invocation are what's recorded in this SUMMARY.
- **Committed in:** not committed (environment-only fix, no tracked file changes)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** The environment fix was necessary before any of this plan's verification could be trusted; no code or scope changes resulted. Flagging this prominently because it will recur for Plans 03-02 and 03-03 (and any other worktree-isolated executor on this project) unless the shell profile's unconditional `VIRTUAL_ENV` export or the worktree-venv-sync step is fixed upstream.

## Issues Encountered
- **Session was interrupted mid-Task-1** by a host process restart before any commit (per the coordinator's resume instruction). On resume, Task 1's `conftest.py`/`test_policy.py`/`policy.py` edits and a draft `engine.py`/`test_engine.py` were already on disk from the prior attempt. These were reviewed against the plan's acceptance criteria (not assumed correct), found substantively complete and correct once the venv issue above was fixed, had one ruff line-length fix applied, and were then committed. A leftover diagnostic probe test (`tests/test_zzz_probe.py`, used to root-cause the venv issue) was deleted before committing -- it was never a plan deliverable.
- **`.planning/phases/03-policy-engine-budget-ledger-mock-llm/` did not exist in this worktree's git history** -- the phase's planning docs (`03-01-PLAN.md`, `03-RESEARCH.md`, etc.) exist only as untracked files in the main repo's working tree (not yet committed to any branch the worktree was created from). The plan file itself, `03-RESEARCH.md`, `PROJECT.md`, `STATE.md`, and `config.json` were read directly from the main repo's absolute paths for context (the Read tool is not worktree-scoped). This `03-01-SUMMARY.md` is written and committed inside the worktree at the path the plan specifies, creating the phase directory there for the first time in this branch's history.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `eacp.engine` and the extended `eacp.policy` are ready for Plan 03-02's `SQLiteBudgetLedger`, which will call `decide()` from inside its own `BEGIN IMMEDIATE` transaction and raise the `PolicyDenied` built here on deny
- `PolicyDenied` is defined but not yet raised anywhere (by design -- Plan 03-02 raises it first)
- **Carry-forward blocker for 03-02/03-03 executors:** the shell's inherited `VIRTUAL_ENV` pointing at the main repo, and the need to `uv sync` a freshly-created worktree `.venv` before trusting any `uv run` output, as documented under Deviations above. Worth fixing upstream (shell profile or worktree bootstrap) rather than rediscovering per-plan.

---
*Phase: 03-policy-engine-budget-ledger-mock-llm*
*Completed: 2026-10-09*
