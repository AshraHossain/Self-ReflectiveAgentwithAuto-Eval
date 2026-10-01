---
phase: 02-core-schema-registry-stores
plan: 01
subsystem: policy
tags: [pydantic, pyyaml, policy-schema, content-hash, sha256, trust-boundary]

requires:
  - phase: 01-stack-decision-scaffold-packaging
    provides: "eacp package skeleton, MissingExtraError, hash-pinned uv.lock with pydantic 2.12.5 + PyYAML 6.0.3"
provides:
  - "eacp.errors: PolicyError, DuplicateEntrypointError, CapabilityError (all ValueError)"
  - "eacp.capabilities: Capability Literal + KNOWN_CAPABILITIES frozenset (durable_approval, inline_approval)"
  - "eacp.policy: MAX_POLICY_BYTES, _StrictLoader, load_yaml_mapping, load_policy_file, Policy, _IDENTITY_FIELDS, _canonical, policy_hash"
  - "tests/conftest.py: policy_yaml fixture (valid 9-field policy builder, overrides + drop=)"
affects: [02-03-registry, 02-02-store-runs-policy_hash-column, phase-3-policy-engine, phase-4-audit-log]

actuals:
  tokens: 4510
  tasks: 3
  commits: 5

plan_head_before: c77761c68ffc91a4ef0d088ac81ec64a50986ac9
plan_head_after: 2ce54886da39cd3f87ef005f5692f27d9b5bf1bc

tech-stack:
  added: []
  patterns:
    - "Single YAML entry point: yaml.load(..., Loader=_StrictLoader) only; no safe_load anywhere in src/"
    - "Every policy-load failure surfaces as PolicyError; ValidationError rendered with include_url=False and without input values"
    - "Field-level StrictInt, never model-level strict; Decimal cost quantized to 1e-6"
    - "Collection fields are list[...] with a sort+reject-duplicates validator (hash stability)"
    - "Content hash = sha256(_canonical(model_dump(mode=json) minus identity fields))"

key-files:
  created:
    - src/eacp/capabilities.py
    - src/eacp/policy.py
    - tests/conftest.py
    - tests/test_policy.py
  modified:
    - src/eacp/errors.py
    - .planning/REQUIREMENTS.md

key-decisions:
  - "PyYAML untyped boundary handled with two targeted inline type-ignores in policy.py (no types-PyYAML stub dependency added)"
  - "load_policy_file reads at most MAX_POLICY_BYTES+1 bytes, so an oversized file is never fully loaded into memory"
  - "Cost quantize InvalidOperation (e.g. 1e40) is converted to a ValueError so it surfaces as PolicyError, not a raw ArithmeticError"
  - "policy_id constrained to ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
  - "POLICY-04 left Pending in REQUIREMENTS.md: hash delivered here, but pinning to run records (02-02) and audit entries (Phase 3/4) is downstream"

patterns-established:
  - "policy_yaml fixture: build a valid doc, change one field to make it invalid"
  - "Hashed-key-set pin test ties the literal set to the real digest via _canonical"

requirements-completed: [POLICY-01, POLICY-02, POLICY-04]

coverage:
  - id: D1
    description: "Strict YAML loader: duplicate keys, non-mapping root, python tags, and oversized docs are all rejected as PolicyError"
    requirement: POLICY-01
    verification:
      - kind: unit
        ref: "tests/test_policy.py::test_duplicate_key_rejected, test_duplicate_key_rejected_in_nested_and_quoted_forms, test_non_mapping_root_rejected, test_python_tag_rejected, test_oversized_document_rejected, test_oversized_file_rejected"
        status: pass
      - kind: other
        ref: "Task 2 AST gate: _StrictLoader is the only PyYAML parse in src/"
        status: pass
    human_judgment: false
  - id: D2
    description: "Strict Policy schema: extra=forbid, all nine fields required, YAML yes rejected for int, plain int accepted for cost, unknown capability and duplicate list entries rejected"
    requirement: POLICY-02
    verification:
      - kind: unit
        ref: "tests/test_policy.py::test_unknown_field_rejected, test_every_limit_field_is_required[x9], test_yaml_bool_rejected_for_int_limit, test_unknown_capability_rejected, test_duplicate_list_entries_rejected, test_error_message_carries_no_environment_paths, test_valid_baseline_loads"
        status: pass
    human_judgment: false
  - id: D3
    description: "Canonical SHA-256 content hash, stable across key/list order, identity fields, decimal formatting and hash seeds; key set pinned"
    requirement: POLICY-04
    verification:
      - kind: unit
        ref: "tests/test_policy.py::test_hash_is_content_addressed, test_hash_changes_when_a_limit_changes[x9], test_hashed_key_set_is_pinned, test_hash_is_stable_across_processes"
        status: pass
    human_judgment: false
  - id: D4
    description: "Capability vocabulary and phase-2 exception types"
    verification:
      - kind: other
        ref: "Task 1 verify script (vocabulary + exception hierarchy + framework-freedom AST check)"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-10-01
status: complete
---

# Phase 2 Plan 1: Policy Layer Summary

**Hardened PyYAML loader (duplicate-key, byte-cap and non-mapping rejection), a frozen nine-field pydantic `Policy` with field-level strictness, and a seed-independent SHA-256 content hash that excludes `policy_id`/`version`.**

## Performance
- **Duration:** ~25 min
- **Started:** 2026-10-01T04:22Z (approx.)
- **Completed:** 2026-10-01T04:48Z
- **Tasks:** 3
- **Files modified:** 6 (5 code/test + REQUIREMENTS.md)

## Accomplishments
- T-02-01 closed: a repeated `max_tokens_per_run` raises `PolicyError` rather than silently taking the last value. Keys are compared after construction, so quoted (`'a'`) and nested duplicates are caught too.
- T-02-02 closed: the byte cap is checked before parsing. The test monkeypatches `yaml.load` to fail if called, which proves the parser never runs on an oversized alias bomb.
- Every failure from both entry points is a `PolicyError`, including edge cases outside the plan that were probed by hand: NaN, inf, `1e40` cost, an unhashable key, invalid UTF-8, and a missing file.
- POLICY-04 hash: 4 `PYTHONHASHSEED` subprocesses produce the same digest, and the 7-key payload is pinned to a literal set and tied to the real digest.
- 42 tests pass (35 new in test_policy.py plus Phase 1's 7). `mypy --strict` and ruff are clean on all touched files, and `uv lock --check` passes.

## Task Commits
1. **Task 1: Exception types, capability vocabulary, policy_yaml fixture** - `a6e04a8` (feat)
2. **Task 2: Strict YAML loader + Policy schema** - `decec62` (test, RED), `93ba4b8` (feat, GREEN)
3. **Task 3: Canonical content hash** - `6ecc3d9` (test, RED), `2ce5488` (feat, GREEN)

## Files Created/Modified
- `src/eacp/errors.py` - adds PolicyError, DuplicateEntrypointError, CapabilityError
- `src/eacp/capabilities.py` - Capability Literal + KNOWN_CAPABILITIES via get_args; docstring records the "earns its place" rule and the four rejected names
- `src/eacp/policy.py` - loader, schema, `_canonical`, `policy_hash`
- `tests/conftest.py` - `policy_yaml` fixture (stdlib + pytest only)
- `tests/test_policy.py` - POLICY-01/02/04 contract (17 test functions, 35 cases)
- `.planning/REQUIREMENTS.md` - POLICY-01, POLICY-02 marked complete

## Decisions Made
See `key-decisions` in frontmatter. The most important: `types-PyYAML` is not in the lock, so `policy.py` uses `# type: ignore[import-untyped]` on the import and `# type: ignore[misc]` on the `SafeLoader` subclass. Sibling plan 02-02's mypy override covers only `langgraph.*`/`crewai.*`/`ag2.*`, so these ignores will not go stale after the merge.

## Deviations from Plan

**1. [Rule 3 - Blocking] Worktree had no venv**
- **Found during:** Task 1 precondition
- **Issue:** `uv run --no-sync python -c "import pydantic, yaml"` failed (fresh worktree `.venv`)
- **Fix:** `uv sync --locked`, which the precondition prescribes. It installs only from the committed lock and adds no dependency.
- **Verification:** precondition re-run printed `2.12.5 6.0.3`. `uv lock --check` passes.

**2. [Rule 3 - Blocking] mypy --strict failed on untyped PyYAML**
- **Found during:** Task 2
- **Issue:** `import-untyped` for yaml, a `misc` error from subclassing `Any`, and `no-any-return`. The fix the plan implied (adding stubs) would mean a new dependency.
- **Fix:** targeted inline ignores plus a typed local for the `construct_mapping` return. The test patches `"yaml.load"` by dotted path instead of reaching through `eacp.policy.yaml`.
- **Files modified:** src/eacp/policy.py, tests/test_policy.py
- **Committed in:** 93ba4b8

**3. [Rule 2 - Missing critical] Cost quantize could leak a raw `decimal.InvalidOperation`**
- **Found during:** Task 2
- **Issue:** `Decimal("1e40").quantize(Decimal("0.000001"))` raises `InvalidOperation`, which is an `ArithmeticError` and not a `ValueError`. It would escape the `PolicyError` wrapping contract.
- **Fix:** the validator converts it to `ValueError("cost is out of range")`.
- **Verification:** an edge probe reported `rejected [cost huge]: ... cost is out of range`
- **Committed in:** 93ba4b8

**4. [Rule 2 - Missing critical] Unhashable YAML keys would raise TypeError in the duplicate check**
- **Found during:** Task 2
- **Fix:** non-hashable keys are skipped in the dedupe check, so SafeLoader's own `ConstructorError` fires and is wrapped as `PolicyError`.
- **Committed in:** 93ba4b8

**5. [Informational] POLICY-04 not marked complete in REQUIREMENTS.md**
- POLICY-04's wording also requires the hash to be pinned to run records (02-02's `runs.policy_hash`) and audit entries (later phase). The `requirements-completed` frontmatter copies the plan's IDs verbatim, as instructed. The REQUIREMENTS.md checkbox is left for the orchestrator to reconcile after the merge.

**6. [Informational] Pin guard not run verbatim**
- The harness blocks `git -C <pinned root>` and heredocs inside worktree-isolated agents. Root identity was confirmed equivalently: `.git` points at `<PINNED_ROOT>/.git/worktrees/agent-a79a20f094b479ea3`. The plan ledger base `c77761c` was recorded in the transcript and this frontmatter instead of a file under the git-dir. Plan verify scripts were run from scratchpad files with the same content.

**Total deviations:** 4 auto-fixed (2 Rule 3, 2 Rule 2) + 2 informational. **Impact:** no scope creep. All fixes keep the single-failure-type contract the plan asked for.

## TDD Gate Compliance
- RED `decec62`, GREEN `93ba4b8`; RED `6ecc3d9`, GREEN `2ce5488`. No REFACTOR commits were needed.
- Both REDs were import-level collection failures that named exactly the missing target: `eacp.policy` first, then `_IDENTITY_FIELDS`/`policy_hash`. Task 2's action declares that as the intended red state. Under tdd.md's strict reading an import-level RED counts as INVALID_RED, so it is flagged here instead of being glossed over.

## Issues Encountered
None blocking. The `VIRTUAL_ENV` mismatch warning from uv is harmless: the parent checkout's venv is ignored in favour of the worktree's own `.venv`.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
Ready for 02-02 (wave sibling, already running in parallel). Wave 2 (02-03) depends on both 02-01 and 02-02. It can import `Policy`, `Capability`, `KNOWN_CAPABILITIES`, `CapabilityError`, `DuplicateEntrypointError` and the `policy_yaml` fixture. Whole-project `pytest` / `mypy --strict` / `ruff check src tests` gates run there.

## Self-Check: PASSED
All 5 created/modified code files exist. Commits a6e04a8, decec62, 93ba4b8, 6ecc3d9 and 2ce5488 are present in `git log c77761c..HEAD`. The working tree is clean.

---
*Phase: 02-core-schema-registry-stores*
*Completed: 2026-10-01*
