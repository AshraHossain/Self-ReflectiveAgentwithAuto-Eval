---
phase: 03-policy-engine-budget-ledger-mock-llm
plan: 02
subsystem: budget-ledger
tags: [sqlite, decimal, cross-process-locking, idempotency, budget-ledger]

# Dependency graph
requires:
  - phase: 03-policy-engine-budget-ledger-mock-llm (plan 01)
    provides: "eacp.engine: pure decide(), Decision, BudgetState, Usage, cost_of(), output_estimate(), and PolicyDenied carrying a Decision"
provides:
  - "eacp.ledger.SQLiteBudgetLedger: admit()/reconcile()/spent_today()/run_usage() under BEGIN IMMEDIATE transactions"
  - "eacp.ledger.Admission and RunUsage frozen dataclasses"
  - "Caller-supplied (run_id, call_key) replay idempotency (G-1), settled now rather than deferred to Phase 5"
affects: [03-03-mock-llm, phase-04-audit-log, phase-05-07-adapters]

actuals:
  tokens: 8018
  tasks: 3
  commits: 3
  plan_head_before: 007ed4fa055a242c4d5818bb42de2c80ef104176
  plan_head_after: fc5a2edd43e1723dfdc44ada6f27412d3dfe4670

tech-stack:
  added: []
  patterns:
    - "isolation_level=None on EVERY sqlite3.connect() call in the module (reads included), never just the write path -- the only way to guarantee legacy implicit-transaction mode never silently reappears"
    - "BEGIN IMMEDIATE wraps read-decide-write as one transaction; ROLLBACK only fires when c.in_transaction (Pitfall 7)"
    - "Reservation rows pin the model price (input/output per-Mtok) at admission time so reconcile() -- which takes no policy argument -- can still compute actual cost later"
    - "Replay short-circuit: an existing (run_id, call_key) row, reconciled or not, returns its Admission without re-running decide() or charging again"
    - "Money as str(Decimal), dates as date.isoformat() -- never a datetime/date object reaches the driver"

key-files:
  created:
    - src/eacp/ledger.py
    - tests/test_ledger.py
  modified: []

key-decisions:
  - "Added two columns beyond the plan's literal reservations schema -- price_input_per_mtok and price_output_per_mtok (nullable, NULL for a ToolCall reservation) -- because reconcile()'s specified signature (admission, usage) takes no policy/model argument, so the price used at admission time must be persisted somewhere for reconcile() to compute actual cost via engine.cost_of(). Documented as a necessary correctness addition (deviation Rule 2), not a scope change."
  - "Replay's reconstructed Decision (_replay_decision) recomputes limit/observed from the current policy + request rather than persisting the original decision's exact fields a second time, since only budget/step state (never double-charging) is load-bearing for G-1 -- the Decision object is informational. Kept simple deliberately rather than adding a generic decision-serialization scheme to the ledger schema."
  - "test_policy_id_with_sql_metacharacters_is_inert routes the hostile value through run_id/call_key (unrestricted free-form strings) rather than Policy.policy_id, because Policy.policy_id is already pattern-restricted by pydantic (_PolicyId regex) and cannot carry a SQL metacharacter in production -- run_id/call_key are the real unrestricted injection surface this ledger accepts."
  - "The 4-process race test pre-creates the ledger file/schema once in the parent before spawning children, avoiding a second, uninteresting race (sqlite3 'database is locked' on the WAL journal-mode switch when 4 processes simultaneously create a brand-new file) that would mask the actual over-admission race this test exists to prove."

requirements-completed: [BUDGET-01, BUDGET-02, BUDGET-03, BUDGET-04]

coverage:
  - id: D1
    description: "admit() reserves an LLM call's estimated tokens/cost and counts a step for both LLM and tool calls under one BEGIN IMMEDIATE transaction; reconcile() replaces the estimate with the actual cost, keyed on the admission's own UTC date"
    requirement: "BUDGET-01"
    verification:
      - kind: unit
        ref: "tests/test_ledger.py#test_admit_reserves_the_estimate_and_reconcile_applies_the_actual"
        status: pass
      - kind: unit
        ref: "tests/test_ledger.py#test_tool_call_admission_counts_a_step_but_reserves_no_tokens"
        status: pass
      - kind: unit
        ref: "tests/test_ledger.py#test_admit_denies_before_the_call_executes_and_changes_nothing"
        status: pass
    human_judgment: false
  - id: D2
    description: "4 processes racing 10 admits each against a cap of exactly 10 admit exactly 10 total, never the 20-39 the legacy-transaction probe measured -- proven under real OS-level multi-process contention, not a single-process approximation"
    requirement: "BUDGET-01"
    verification:
      - kind: integration
        ref: "tests/test_ledger.py#test_four_processes_race_to_the_cap"
        status: pass
    human_judgment: false
  - id: D3
    description: "reconcile() applies actual-minus-estimate to the admission's own UTC date, correctly across a midnight crossing via an injected clock, and raises KeyError on a double reconcile without double-applying or undoing the first delta"
    requirement: "BUDGET-02"
    verification:
      - kind: unit
        ref: "tests/test_ledger.py#test_reconcile_applies_to_the_admission_date_not_todays_date"
        status: pass
      - kind: unit
        ref: "tests/test_ledger.py#test_double_reconcile_raises_keyerror"
        status: pass
      - kind: unit
        ref: "tests/test_ledger.py#test_missing_usage_charges_the_estimate_not_zero"
        status: pass
    human_judgment: false
  - id: D4
    description: "The daily spend counter is keyed by (policy_id, utc_date), persists across a process restart, and a fresh process reads back exactly what a prior process wrote"
    requirement: "BUDGET-03"
    verification:
      - kind: unit
        ref: "tests/test_ledger.py#test_reopen_reads_back_prior_state"
        status: pass
      - kind: integration
        ref: "tests/test_ledger.py#test_spend_survives_process_restart"
        status: pass
    human_judgment: false
  - id: D5
    description: "max_steps denies the next call independent of token/cost headroom, counting a tool call toward the ceiling exactly like an LLM call"
    requirement: "BUDGET-04"
    verification:
      - kind: unit
        ref: "tests/test_ledger.py#test_max_steps_denies_the_next_call_independent_of_tokens_and_cost"
        status: pass
    human_judgment: false
  - id: D6
    description: "A replayed admit() for the same (run_id, call_key) never double-charges, whether in-flight or already reconciled (G-1)"
    verification:
      - kind: unit
        ref: "tests/test_ledger.py#test_replayed_admit_is_not_charged_twice"
        status: pass
    human_judgment: false
  - id: D7
    description: "T-03-06/07/08 are each closed by a behavioral test, and T-03-06/07 additionally by a static, comment-immune gate (isolation_level=None AST check, no-f-string-to-execute AST check)"
    verification:
      - kind: unit
        ref: "tests/test_ledger.py#test_ledger_file_is_not_world_readable"
        status: pass
      - kind: unit
        ref: "tests/test_ledger.py#test_policy_id_with_sql_metacharacters_is_inert"
        status: pass
      - kind: other
        ref: "AST gate (plan 03-02-PLAN.md Task 1 verify): every sqlite3.connect() call carries isolation_level=None; no SQL-executing call receives an f-string/percent-format/.format() result"
        status: pass
    human_judgment: false

duration: 70min
completed: 2026-10-09
status: complete
---

# Phase 3 Plan 02: SQLite Budget Ledger Summary

**`SQLiteBudgetLedger` enforces BUDGET-01 through BUDGET-04 with real cross-process atomicity: `isolation_level=None` + `BEGIN IMMEDIATE` admits exactly 10 of 10 under a verified 4-process race that the legacy transaction style over-admits 20-39 times.**

## Performance

- **Duration:** 70 min
- **Completed:** 2026-10-09
- **Tasks:** 3
- **Files modified:** 2 (both created)

## Accomplishments
- `src/eacp/ledger.py` built from scratch: `SQLiteBudgetLedger` with `admit()`, `reconcile()`, `spent_today()`, `run_usage()`, plus `Admission`/`RunUsage` frozen dataclasses
- Every `sqlite3.connect()` call in the module -- reads included -- uses `isolation_level=None`, gated by an AST check; `admit()`/`reconcile()` run inside `BEGIN IMMEDIATE`; `ROLLBACK` only fires when `c.in_transaction` (Pitfall 7)
- G-1 replay idempotency settled now: `reservations` is keyed `(run_id, call_key)`; an existing row -- in flight or already reconciled -- short-circuits `admit()` without charging budget again
- `reconcile()` corrects the admission's own UTC date, never today's, proven across an injected-clock midnight crossing; a `MISSING` usage reading charges the estimate (never zero) and increments `missing_usage`; a double reconcile raises `KeyError`
- Cross-process correctness proven for real, not approximated: 4 `subprocess.Popen` children racing 10 admits each against a cap of exactly 10 admit exactly 10 (run 5x locally with no flake); a fresh `subprocess.run` child reads back exactly what a parent process wrote; the ledger file and its WAL sidecars are mode 0600 while a connection holds them open
- 13 tests in `tests/test_ledger.py`; full suite (Phase 1+2+3) is 117 passed; `mypy --strict`, ruff, and `uv lock --check` all clean

## Task Commits

Each task was committed atomically:

1. **Task 1: Ledger schema, BEGIN IMMEDIATE transaction, admit()/reconcile() single-process path** - `8808c25` (feat)
2. **Task 2: Deny path, idempotent replay, MISSING usage, cross-midnight reconcile** - `3e8353b` (test)
3. **Task 3: Cross-process correctness -- race, restart, and file permissions** - `fc5a2ed` (test)

**Plan metadata:** committed separately with this SUMMARY.

## Files Created/Modified
- `src/eacp/ledger.py` - New `SQLiteBudgetLedger`: schema (`daily_spend`, `run_usage`, `reservations`), `_tx()` BEGIN IMMEDIATE contextmanager, `admit()`, `reconcile()`, `spent_today()`, `run_usage()`
- `tests/test_ledger.py` - BUDGET-01 through BUDGET-04's executable contract: single-process tracer proof, deny/replay/MISSING/cross-midnight tests, and the 4-process race/restart/permissions/SQL-metacharacter proofs

## Decisions Made
- Added `price_input_per_mtok`/`price_output_per_mtok` columns to `reservations` (nullable, NULL for a `ToolCall`) so `reconcile()` -- whose plan-specified signature takes no policy/model argument -- can still compute actual cost from the price pinned at admission time
- `_replay_decision()` recomputes a replay's `Decision.limit`/`observed` from the current policy + request rather than persisting the original decision's exact fields a second time; only the budget/step state (never double-charging) is load-bearing for G-1
- `test_policy_id_with_sql_metacharacters_is_inert` routes the hostile value through `run_id`/`call_key` (the real unrestricted injection surface) rather than `Policy.policy_id`, which pydantic's `_PolicyId` pattern already blocks from ever carrying a SQL metacharacter in production
- The 4-process race test pre-creates the ledger file/schema once in the parent before spawning children, to avoid a second, uninteresting "database is locked" race on the WAL journal-mode switch of a brand-new file that would mask the over-admission race the test exists to prove

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Worktree was stale: missing Plan 03-01's merge, and venv not synced**
- **Found during:** pre-execution setup, before Task 1
- **Issue:** This worktree's branch HEAD (`15cf71a`) predated Plan 03-01's merge to `main` (`9c0c5a4`/`007ed4f`), so `src/eacp/engine.py`, the extended `Policy` schema, and `PolicyDenied` did not exist on this branch yet, despite the dispatch objective stating the worktree's base "should already include it". Separately, per the known-environment-bug note, the worktree's `.venv` was never `uv sync`'d and the shell's inherited `VIRTUAL_ENV` pointed at the main repo's `.venv`.
- **Fix:** Verified the worktree branch was a clean ancestor of `main` (`git merge-base --is-ancestor HEAD main`), then fast-forwarded (`git merge --ff-only main`) to pick up Plan 03-01's commits non-destructively. Ran `VIRTUAL_ENV= uv sync` once, then confirmed `VIRTUAL_ENV= uv run --no-sync python -c "import eacp; print(eacp.__file__)"` resolved to this worktree's own `src/eacp`, not the main repo's.
- **Files modified:** none (branch/environment only).
- **Verification:** Baseline `VIRTUAL_ENV= uv run --no-sync pytest -q` showed 104 passed (Phase 1+2+3's Plan 01 baseline) before any Plan 02 code was written.
- **Committed in:** not committed (the fast-forward merge carried Plan 03-01's own already-committed history; no new commit was created by this fix)

**2. [Rule 2 - Missing Critical] Added price snapshot columns to the reservations schema**
- **Found during:** Task 1, while implementing `reconcile()`
- **Issue:** The plan's literal `reservations` schema (frontmatter action text) has no price columns, but `reconcile(self, admission: Admission, usage: Usage) -> None` takes no policy/model argument, so there was no way to look up the `ModelPrice` needed for `engine.cost_of()` when computing the actual cost from real usage.
- **Fix:** Added `price_input_per_mtok`/`price_output_per_mtok` (nullable TEXT) to `reservations`, populated at `admit()` time from `policy.model_prices[request.model]` for an `LlmCall`, left `NULL` for a `ToolCall`. `reconcile()` reconstructs a `ModelPrice` from these two columns.
- **Files modified:** `src/eacp/ledger.py`
- **Verification:** `test_admit_reserves_the_estimate_and_reconcile_applies_the_actual` proves the actual cost is computed correctly from scripted usage that deliberately differs from the estimate.
- **Committed in:** `8808c25` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing-critical)
**Impact on plan:** The worktree fast-forward was necessary before any of this plan's code could even import its Plan 03-01 dependencies; no scope change resulted. The schema addition was necessary for `reconcile()` to satisfy its own specified signature; no scope change resulted.

## Issues Encountered
- The 4-process race test (`test_four_processes_race_to_the_cap`) initially failed with `sqlite3.OperationalError: database is locked` -- not from the admission race itself, but from all 4 child processes independently racing the WAL journal-mode switch on a ledger file that did not yet exist. Fixed by having the parent test construct `SQLiteBudgetLedger(db)` once (creating the schema/WAL file) before spawning any children, matching the realistic deployment shape where a ledger file always pre-exists before concurrent adapters open it. Re-ran the test 5 consecutive times afterward with no flake.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `eacp.ledger.SQLiteBudgetLedger` is ready for Plan 03-03's `MockLLM`, which will be driven through `admit()`/`reconcile()` in an end-to-end early-stop test (the runaway mock stopped before the blocking call)
- Phase 4's audit log can read `Admission`/`Decision` directly; `Decision`'s `Decimal`-typed fields still need `str()` rendering before `json.dumps` (G-3, documented in `engine.py`, not built here)
- No `BudgetLedger` Protocol was added (per 03-RESEARCH.md Alternatives) -- one concrete implementation exists; add a Protocol if/when a second ledger backend appears
- Carry-forward for any future worktree-isolated executor on this project: verify `git merge-base --is-ancestor HEAD main` before assuming a worktree's base includes the latest merged plan, and always `VIRTUAL_ENV= uv sync` once per fresh worktree before trusting any `uv run` output

---
*Phase: 03-policy-engine-budget-ledger-mock-llm*
*Completed: 2026-10-09*

## Self-Check: PASSED

- FOUND: src/eacp/ledger.py
- FOUND: tests/test_ledger.py
- FOUND: 8808c25 (Task 1 commit)
- FOUND: 3e8353b (Task 2 commit)
- FOUND: fc5a2ed (Task 3 commit)
