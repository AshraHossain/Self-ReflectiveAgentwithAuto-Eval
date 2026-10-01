---
phase: 02-core-schema-registry-stores
plan: 02
subsystem: database
tags: [sqlite, run-history, protocol, wal, mypy, pytest, trace-03]

requires:
  - phase: 01-packaging-skeleton
    provides: core-only package layout, uv lockfile, pytest/mypy/ruff config, adapter placeholders
provides:
  - "eacp.store.RunStore: synchronous six-method Protocol (start_run, finish_run, append_step, get_run, list_runs, list_steps)"
  - "eacp.store.SQLiteRunStore: v1 implementation, WAL, connection-per-call, per-connection foreign keys, user_version=1"
  - "eacp.store.RunRecord / StepRecord (frozen slotted dataclasses), RunStatus Literal, utc_now(), MAX_LIST_LIMIT"
  - "pytest filterwarnings error::DeprecationWarning (proven to fire)"
  - "[[tool.mypy.overrides]] for langgraph.*/crewai.*/ag2.*: mypy --strict is green on a core-only host"
affects: [02-03, phase-4-approvals, phase-5-tracing, phase-6, phase-7]

actuals:
  tokens: 5030
  tasks: 3
  commits: 5

plan_head_before: c77761c68ffc91a4ef0d088ac81ec64a50986ac9
plan_head_after: 45fe23981cff7fe26845f47775a7ac39cd5262cf

tech-stack:
  added: []
  patterns:
    - "Structural Protocol conformance proven statically: `store: RunStore = SQLiteRunStore(...)` under mypy --strict; no runtime protocol check"
    - "Connection-per-call sqlite3 with `with closing(conn) as c, c:` = one transaction per method"
    - "Timestamps are ISO-8601 UTC microsecond TEXT via utc_now(); never datetime objects to the driver"
    - "Optional SQL filters: literal fragments list + parallel bound-args list; table names/sort direction are authored literals"

key-files:
  created:
    - src/eacp/store.py
    - tests/test_store.py
  modified:
    - pyproject.toml
    - .planning/REQUIREMENTS.md

key-decisions:
  - "The DB file is created (touch mode=0o600) and chmod'ed 0600 BEFORE the first sqlite3.connect, so -wal/-shm are born 0600 too, not just fixed up after"
  - "RunStatus 'denied' = governance halt (approval refused or budget block); 'failed' = crash"
  - "MAX_LIST_LIMIT=1000 exported as a module constant so the clamp test asserts against the real ceiling"
  - "Injection test also requires a benign filter to match, so an always-empty list_runs cannot pass it vacuously"

patterns-established:
  - "RED commits for TDD tasks ship an interface-only skeleton so RED is an assertion failure, not an ImportError"

requirements-completed: [TRACE-03]

coverage:
  - id: D1
    description: "pytest turns DeprecationWarning into failure; mypy --strict green on core-only host via scoped overrides"
    verification:
      - kind: other
        ref: "Task 1 verify: tomllib config assertions + probe test in tests/ exits nonzero + `mypy --strict src/eacp/adapters/` (3 errors -> 0) + `uv lock --check`"
        status: pass
    human_judgment: false
  - id: D2
    description: "RunStore Protocol + SQLiteRunStore write path: roundtrip, in-flight visibility, unknown finish raises, orphan/duplicate step rejected, cross-thread, reopen with WAL + user_version=1"
    requirement: TRACE-03
    verification:
      - kind: unit
        ref: "tests/test_store.py (9 tests incl. test_sqlite_store_satisfies_protocol, test_run_roundtrip, test_store_survives_reopen)"
        status: pass
      - kind: other
        ref: "uv run --no-sync mypy --strict src/eacp/store.py tests/test_store.py (static Protocol conformance)"
        status: pass
      - kind: integration
        ref: "Task 2 verify script (AST framework-free gate, sys.modules gate, end-to-end roundtrip)"
        status: pass
    human_judgment: false
  - id: D3
    description: "list_runs filters/ordering, SQL-injection inertness (T-02-06), limit clamp (T-02-10), owner-only db + sidecars (T-02-11)"
    requirement: TRACE-03
    verification:
      - kind: unit
        ref: "tests/test_store.py::test_list_runs_filters, test_filter_value_is_parameterized, test_list_runs_limit_is_clamped, test_store_file_is_not_world_readable"
        status: pass
      - kind: other
        ref: "Task 3 verify: AST gate (no f-string/%/.format reaches execute) + behavioural script (sidecars present and 0600)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Store works with zero frameworks and no dev group installed"
    requirement: TRACE-03
    verification:
      - kind: integration
        ref: "scratch copy: uv sync --locked --no-default-groups; find_spec(langgraph/crewai/ag2/pytest) all None; store roundtrip + list_runs OK"
        status: pass
    human_judgment: false

duration: ~10min
completed: 2026-09-30
status: complete
---

# Phase 2 Plan 2: Run-History Store Summary

**A synchronous `RunStore` Protocol plus `SQLiteRunStore` (WAL, connection-per-call, per-connection foreign keys, bound-parameter filters, a `[1, 1000]` limit clamp, files owner-only at 0600), with conformance proven by `mypy --strict`, which now runs green on a core-only host.**

## Performance
- **Duration:** ~10 min
- **Started:** ~2026-10-01T04:39Z (approximate; the start timestamp was not captured)
- **Completed:** 2026-10-01T04:48Z
- **Tasks:** 3 (Tasks 2 and 3 were TDD, each with a RED and a GREEN commit)
- **Files modified:** 3 code/config files, plus REQUIREMENTS.md

## Accomplishments
- TRACE-03 works: a run is started, stays visible while in flight, gets three steps appended in `seq` order, is finished, and reads back equal to the expected `RunRecord`/`StepRecord`, with the JSON blobs intact.
- Database-enforced integrity: an orphan step fails the foreign key, a duplicate `(run_id, seq)` fails the composite primary key, and `finish_run` raises `KeyError` on an unknown id.
- Thread-safe and cross-instance: reads and writes work across threads, and a reopened store reads back WAL with `user_version=1`.
- Threats T-02-06, T-02-10 and T-02-11 are each closed by a behavioural test, and T-02-06 also by the AST gate. `runs.db`, `-wal` and `-shm` were measured at 0644 before the change and 0600 after.
- `filterwarnings = ["error::DeprecationWarning"]` is in place and was proven to fire with a probe test in `tests/`. Whole-project `mypy --strict` went from 3 errors to "no issues found in 12 source files".

## Task Commits
1. **Task 1: pytest/mypy gates (pyproject.toml)**: `4cc1fa3` (chore)
2. **Task 2: Protocol, records, schema, write path**: RED `b0d6ed2` (test), GREEN `18a975e` (feat)
3. **Task 3: read path, query hardening, file permissions**: RED `b228600` (test), GREEN `45fe239` (feat)

No refactor commit was needed.

## Files Created/Modified
- `src/eacp/store.py`: `RunStatus`, `RunRecord`, `StepRecord`, `RunStore` Protocol, `SQLiteRunStore`, `utc_now()`, `MAX_LIST_LIMIT`. Stdlib only.
- `tests/test_store.py`: 13 tests, all on `tmp_path`, including the annotated static conformance probe.
- `pyproject.toml`: `filterwarnings` entry and a scoped `[[tool.mypy.overrides]]` block. No dependency tables were touched, and `uv lock --check` passes.
- `.planning/REQUIREMENTS.md`: TRACE-03 marked complete.

## Decisions Made
- The file is set to 0600 before the first connect (`touch(mode=0o600)` then `chmod(0o600)`), not after. SQLite creates the sidecars with the database file's mode, so this way they never exist at 0644.
- `denied` is a governance halt (APPROVAL-03 or BUDGET-01) and `failed` is a crash. This follows the plan's statement that these "are different outcomes from a crash".
- I added `test_utc_now_is_canonical_iso8601`, a small extra test that pins the fixed-width UTC microsecond format the lexicographic ordering depends on.

## Deviations from Plan

**1. [Rule 1 - Bug] Hostile `since` value in my own T-02-06 test did not discriminate**
- **Found during:** Task 3 GREEN
- **Issue:** `since="' OR 1=1;--"` bound as a string legitimately sorts before `"2026-..."`, so `started_at >= ?` matched. The test failed against a correct implementation.
- **Fix:** Changed the value to `"9999' OR '1'='1"`. Bound, it sorts after every timestamp and matches nothing. Interpolated, it would match everything.
- **Files modified:** tests/test_store.py
- **Verification:** 20/20 tests pass and the Task 3 verify script passes.
- **Committed in:** `45fe239`

**2. [Rule 3 - Blocking] Executor-environment adaptations (no code impact)**
- The worktree had no venv, so `uv run --no-sync` first created an empty one and ran PATH tools. I ran `uv sync --locked` (lockfile-only, core plus dev group, no extras) so every gate ran against the worktree's own environment.
- The harness forbids `git -C <main checkout>`, so the `<project_root_pin>` guard could not run verbatim. I substituted `git rev-parse --git-common-dir`, which resolves to `<PINNED_ROOT>/.git`; that confirms this worktree belongs to the pinned repo.
- Compound git expressions were refused by the harness, so I did not write the `gsd-plan-head-before` ledger file. `commits:` was measured directly with `git rev-list --count c77761c..HEAD` = 5 against the fixed, known plan base.
- I ran the plan's `uv sync --locked --no-default-groups` check in a scratch copy rather than the worktree, so the dev venv stayed intact.

**Total deviations:** 1 auto-fixed test bug and 1 environment adaptation (no product-code impact).
**Impact on plan:** None on scope. Every `<verify>`, `<acceptance>` and `<verification>` gate was run and passes.

## TDD Gate Compliance
- RED commits `b0d6ed2` and `b228600` both failed on assertions for the planned behaviour (8/8 and 4/4 target tests), not on import errors. Each RED commit includes an interface-only skeleton of `store.py` (and later the `MAX_LIST_LIMIT` constant) to make that possible.
- `test_sqlite_store_satisfies_protocol` passes at RED by design: its real gate is the mypy annotation.
- GREEN commits `18a975e` and `45fe239` pass.

## Issues Encountered
None beyond the deviations above.

## Known Stubs
None. The no-op skeleton existed only in RED commits and was fully replaced by GREEN.

## User Setup Required
None. No external service configuration is required.

## Next Phase Readiness
- Ready for 02-01 (the wave sibling, running in parallel). Wave 2 (02-03) depends on both 02-01 and 02-02 completing.
- I did not add a `.gitignore` entry for `runs.db*` (RESEARCH's Runtime State Inventory suggests one) because `.gitignore` is outside this plan's `files_modified`. 02-03 or a later phase should add `runs.db`, `runs.db-wal` and `runs.db-shm`.
- Phases 4, 5, 6 and 7 can type against `eacp.store.RunStore`. The ag2 adapter should bridge with a thread offload per D-06.

## Self-Check: PASSED
- Files exist: src/eacp/store.py, tests/test_store.py, 02-02-SUMMARY.md.
- Commits exist on the branch: 4cc1fa3, b0d6ed2, 18a975e, b228600, 45fe239.
- The working tree is clean, and the TDD RED (`test(02-02)`) and GREEN (`feat(02-02)`) gate commits are present.

---
*Phase: 02-core-schema-registry-stores*
*Completed: 2026-09-30*
