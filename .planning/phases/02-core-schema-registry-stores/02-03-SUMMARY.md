---
phase: 02-core-schema-registry-stores
plan: 03
subsystem: registry
tags: [registry, workflow-schema, capability-gate, allowlist, pydantic, security]
status: complete
requires:
  - phase: 02-01
    provides: "Policy schema (policy.requires, policy_id, _PolicyId pattern), Capability Literal + KNOWN_CAPABILITIES, CapabilityError / DuplicateEntrypointError"
  - phase: 01
    provides: "eacp.backends load_backend_module / available_backends lazy-import chokepoint; adapter placeholder shape (BACKEND, FRAMEWORK_VERSION)"
provides:
  - "eacp.registry: BackendType, Workflow, register_entrypoint, resolve_entrypoint, register_workflow, get_workflow"
  - "CAPABILITIES constant on each adapter (langgraph: durable+inline; crewai, ag2: inline)"
  - "tests/test_registry.py: WORKFLOW-01/02/03 executable contract incl. AST import-machinery gate"
affects: [phase-04-approval-cli, phase-05-langgraph, phase-06-crewai, phase-07-ag2-conformance, docs-capability-matrix]
actuals:
  tokens: 4385
  tasks: 3
  commits: 5
plan_head_before: b6bf332a1a003b95a717ac3f80bf0970bc0993fa
plan_head_after: 9cb696ede166b4119848473c6b6dd928488b0ebe
tech-stack:
  added: []
  patterns:
    - "Allowlist dict + register/resolve pair mirroring backends._BACKENDS (ValueError listing known keys, from None)"
    - "Capability gate as a set difference against the adapter's own declaration (D-07), reached only via load_backend_module"
    - "Gate order cheapest-and-purest first: entrypoint -> backend name -> backend module"
    - "Security gates asserted from the syntax tree, not text grep"
key-files:
  created:
    - src/eacp/registry.py
    - tests/test_registry.py
  modified:
    - src/eacp/adapters/langgraph_adapter.py
    - src/eacp/adapters/crewai_adapter.py
    - src/eacp/adapters/ag2_adapter.py
key-decisions:
  - "Workflow is frozen=True as well as extra=forbid: a mutable registered Workflow could have its entrypoint/backend changed after passing the gates"
  - "Workflow.policy_id reuses policy.py's _PolicyId pattern so a workflow can name exactly the ids a Policy can carry; id and entrypoint share registry's _NAME_RE"
  - "Duplicate-id and policy_id-mismatch checks run before gate (1): both are pure comparisons, so they cannot disturb the entrypoint-before-module ordering"
  - "Unknown-capability check on the adapter's declaration runs before the shortfall check: an invalid declaration is reported regardless of what the policy requires"
patterns-established:
  - "Tests isolate module-global registries via autouse monkeypatch.setattr(reg, '_ENTRYPOINTS'/'_WORKFLOWS', {})"
  - "Capability tests monkeypatch reg.load_backend_module with a SimpleNamespace fake; the gate-order test deliberately uses the real loader"
requirements-completed: [WORKFLOW-01, WORKFLOW-02, WORKFLOW-03]
coverage:
  - id: D1
    description: "Adapters declare their own CAPABILITIES (D-07); no central table in registry.py"
    verification:
      - {kind: automated, ref: "Task 1 <verify> AST read of each adapter + registry literal check", status: pass}
    human_judgment: false
  - id: D2
    description: "Workflow schema: exactly six required fields, topology fields rejected, Literal matches available_backends()"
    requirement: WORKFLOW-01
    verification:
      - {kind: automated, ref: "tests/test_registry.py::test_topology_fields_rejected, test_workflow_schema_fields, test_backend_literal_matches_backends_module", status: pass}
      - {kind: automated, ref: "Task 2 <verify> inline script", status: pass}
    human_judgment: false
  - id: D3
    description: "Entrypoint allowlist: charset gate, re-registration refused without mutation, unknown name rejected listing registered names; registry.py has no import machinery"
    requirement: WORKFLOW-02
    verification:
      - {kind: automated, ref: "tests/test_registry.py::test_entrypoint_name_charset, test_duplicate_entrypoint_registration_rejected, test_unregistered_entrypoint_rejected, test_registry_has_no_import_machinery", status: pass}
      - {kind: automated, ref: "Task 2 <verify> T-02-04 AST gate (run as written)", status: pass}
    human_judgment: false
  - id: D4
    description: "Capability gate: shortfall raises CapabilityError naming both sides; match/empty-requires accepted; unknown adapter capability, policy_id mismatch, duplicate workflow id rejected; gate order verified against real loader; registry imports framework-free"
    requirement: WORKFLOW-03
    verification:
      - {kind: automated, ref: "tests/test_registry.py (14 test functions, 22 cases)", status: pass}
      - {kind: automated, ref: "Task 3 <verify> inline script + --no-default-groups framework-free import", status: pass}
      - {kind: automated, ref: "mutation check: moving load_backend_module before gate (1) makes test_gate_order_unknown_entrypoint_wins fail with MissingExtraError", status: pass}
    human_judgment: false
duration: "942min wall clock (see Performance)"
completed: 2026-10-02
---

# Phase 2 Plan 3: Workflow Registry Summary

**Process-local workflow registry with an entrypoint allowlist (charset-gated, hijack-proof), a six-field topology-free `Workflow` schema, and a WORKFLOW-03 capability gate that rejects e.g. a `durable_approval` policy on inline-only CrewAI/ag2 at registration time, reading each adapter's own `CAPABILITIES` via `load_backend_module` with zero import machinery in `registry.py`.**

## Performance

- **Duration:** 942 min wall clock (02:24Z to 18:07Z). Active work was a small fraction of that; the gap is host/session suspension, not execution time.
- **Started:** 2026-10-02T02:24:57Z
- **Completed:** 2026-10-02T18:07:21Z
- **Tasks:** 3/3
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments

- `CAPABILITIES: frozenset[Capability]` on each adapter, next to `BACKEND`/`FRAMEWORK_VERSION`: LangGraph `{durable_approval, inline_approval}`, CrewAI and ag2 `{inline_approval}` (D-07, APPROVAL-04/05).
- `Workflow` pydantic model: `extra="forbid"`, `frozen=True`, exactly `id, name, description, backend_type, entrypoint, policy_id`, all required; `nodes`/`agents`/`edges` rejected (WORKFLOW-01).
- `register_entrypoint` / `resolve_entrypoint`: `^[a-z0-9][a-z0-9_-]{0,63}$` charset, `DuplicateEntrypointError` on re-registration leaving the original intact (T-02-05), unknown name lists registered ones (WORKFLOW-02).
- `register_workflow(workflow, policy)` / `get_workflow`: gates in order entrypoint, backend name, then `load_backend_module` + set difference; unknown adapter capabilities rejected; policy_id mismatch (T-02-14) and duplicate id (T-02-13) rejected (WORKFLOW-03).
- D-13 (not persisted, runs table self-contained for Phase 4) and T-02-12 (durable claim unverified, transferred to CONFORM-01 with the test shape) written into docstrings.

## Task Commits

1. **Task 1: Adapter CAPABILITIES (D-07)** - `ebdead3` (feat)
2. **Task 2: Entrypoint allowlist + Workflow schema** - `817e34b` (test, RED), `8ce2be3` (feat, GREEN)
3. **Task 3: Capability gate** - `134ca56` (test, RED), `9cb696e` (feat, GREEN)

No REFACTOR commits: nothing needed cleaning after GREEN.

## Files Created/Modified

- `src/eacp/registry.py` - allowlist, `Workflow` schema, `register_workflow` / `get_workflow` capability gate (128 lines)
- `tests/test_registry.py` - 14 test functions / 22 cases, including the AST import-machinery gate (220 lines)
- `src/eacp/adapters/langgraph_adapter.py`, `crewai_adapter.py`, `ag2_adapter.py` - `CAPABILITIES` constant + `from eacp.capabilities import Capability` (placed after the framework import, so a missing framework still raises first and `backends.py`'s error translation is unchanged)

## Decisions Made

- `Workflow` is `frozen=True`: without it a registered workflow could be mutated after passing the gates, bypassing them.
- `Workflow.policy_id` reuses `policy._PolicyId` (rung 2: already in the codebase) rather than inventing a third pattern.
- Duplicate-id and policy-id-mismatch checks run first: both are pure comparisons and cannot affect the entrypoint-before-module ordering Pitfall 5 cares about.
- Unknown-capability check precedes the shortfall check so an invalid adapter declaration is always reported.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Dev tools missing from the venv**
- **Found during:** Task 1 verify
- **Issue:** `pytest`/`mypy`/`ruff` failed to spawn; the venv had been left in a `--no-default-groups` state by an earlier run.
- **Fix:** `uv sync --locked` (restores the dev group from the committed lockfile; nothing new installed or resolved).
- **Files modified:** none (venv only)
- **Verification:** 55 passed, mypy and ruff clean, `uv lock --check` clean.

**2. [Rule 2 - Missing critical] `Workflow` made immutable**
- **Found during:** Task 2
- **Issue:** The plan specifies `extra="forbid"` only; a mutable model stored in `_WORKFLOWS` could have `entrypoint`/`backend_type` reassigned after the gates passed.
- **Fix:** `ConfigDict(extra="forbid", frozen=True)`, matching `Policy`.
- **Files modified:** `src/eacp/registry.py`
- **Commit:** `8ce2be3`

**Total:** 2 auto-fixed (1 environment, 1 hardening). No scope change; no architectural decisions.

**Process note:** commits landed directly on `main`, as the orchestrator instructed for this sequential wave (`git.branching_strategy: none`, same as Wave 1's merges).

## Issues Encountered

None beyond the venv state above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 2 complete, ready for /gsd-verify-work 2.

- Phase 4: the registry is process-local by design; the approval CLI must read from the `runs` table, never from `eacp.registry`.
- Phase 7 / CONFORM-01 inherits T-02-12: "for each adapter, durable approval is declared if and only if a run survives a process exit".
- A2 (ag2 durable?) remains a one-line edit in `ag2_adapter.py` if its snapshot mechanism qualifies.

## TDD Gate Compliance

RED `817e34b`, `134ca56` (collection-time ImportError on the not-yet-existing names, the phase's established precedent for new modules); GREEN `8ce2be3`, `9cb696e`. Gate order also mutation-tested: moving `load_backend_module` ahead of gate (1) makes `test_gate_order_unknown_entrypoint_wins` fail with a real `MissingExtraError`.

## Self-Check: PASSED

All 5 plan files present; commits ebdead3, 817e34b, 8ce2be3, 134ca56, 9cb696e found.
