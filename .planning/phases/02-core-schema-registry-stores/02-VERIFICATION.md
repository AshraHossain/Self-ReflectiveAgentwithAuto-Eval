---
phase: 02-core-schema-registry-stores
verified: 2026-10-02T00:00:00Z
status: passed
score: 4/4 must-haves verified
covered_files: [".planning/phases/02-core-schema-registry-stores/02-01-PLAN.md", ".planning/phases/02-core-schema-registry-stores/02-01-SUMMARY.md", ".planning/phases/02-core-schema-registry-stores/02-02-PLAN.md", ".planning/phases/02-core-schema-registry-stores/02-02-SUMMARY.md", ".planning/phases/02-core-schema-registry-stores/02-03-PLAN.md", ".planning/phases/02-core-schema-registry-stores/02-03-SUMMARY.md", ".planning/phases/02-core-schema-registry-stores/02-REVIEW-DISPOSITION.md", ".planning/phases/02-core-schema-registry-stores/02-REVIEW.md", ".planning/phases/02-core-schema-registry-stores/02-VALIDATION.md", "pyproject.toml", "src/eacp/adapters/ag2_adapter.py", "src/eacp/adapters/crewai_adapter.py", "src/eacp/adapters/langgraph_adapter.py", "src/eacp/capabilities.py", "src/eacp/errors.py", "src/eacp/policy.py", "src/eacp/registry.py", "src/eacp/store.py", "tests/conftest.py", "tests/test_policy.py", "tests/test_registry.py", "tests/test_store.py"]
covered_digest: "v2:sha256:74d9a0c6436d04a4cf0073f5a4c9e2ac5d3295c61cff7825c08f801e9fa37b74"
behavior_unverified: 0
overrides_applied: 0
---

# Phase 2: Core Schema, Registry & Stores Verification Report

**Phase Goal:** Policies and workflows are declared, validated, and stored the same way regardless of which framework will eventually run them.
**Verified:** 2026-10-02T00:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A policy YAML file with an unknown/forbidden field is rejected at load time (`safe_load`-derived + fixed schema, no DSL) | ✓ VERIFIED | Independent script constructed a valid policy plus one extra field `experimental_dsl_hook` and called `load_policy_file`. Raised `PolicyError: ...invalid policy: experimental_dsl_hook: Extra inputs are not permitted`. `src/eacp/policy.py` uses a single `_StrictLoader` (subclass of `yaml.SafeLoader`) as the sole PyYAML entry point in `src/`, and `Policy` uses `extra="forbid"` — no custom DSL parser exists anywhere in the package. |
| 2 | Every policy is content-hashed and that hash is retrievable and stable for identical policy content | ✓ VERIFIED | Independent script built two policy documents differing in key order, list order, `policy_id`, `version`, and `10.00` vs `10.0`; `policy_hash()` returned the identical 64-char SHA-256 hex digest for both (`5fe643...0330ff`). Changing `max_tokens_per_run` on one produced a different hash (`c1909b...88a1`), proving the hash is content-sensitive, not constant. |
| 3 | A workflow entrypoint not on the allowlist is rejected at registration time, not at run time | ✓ VERIFIED | Independent script built a `Workflow` with `entrypoint="never_registered_anywhere"` and called `register_workflow(wf, policy)` directly (no run attempted). Raised `ValueError: Unknown entrypoint 'never_registered_anywhere'. Registered: []` — `register_workflow`'s gate order resolves the entrypoint (gate 1, a pure dict lookup) before gate 2 (backend name) and gate 3 (`load_backend_module` + capability comparison), so the rejection happens purely at registration with zero backend code touched. |
| 4 | Run history can be written to and read back from the SQLite store via its `Protocol` interface with zero framework code imported | ✓ VERIFIED | Confirmed `langgraph`, `crewai`, `ag2` are genuinely not installed in this venv (`importlib.util.find_spec` returns `None` for all three). Independent script imported `eacp.store`, asserted no framework module was in `sys.modules`, then ran `start_run` → `append_step` → `finish_run` → `get_run`/`list_steps` through a `store: RunStore = SQLiteRunStore(...)`-typed variable and confirmed every written value (status, metrics, step name) round-tripped exactly. |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/eacp/errors.py` | `PolicyError`, `DuplicateEntrypointError`, `CapabilityError` alongside Phase 1's `MissingExtraError` | ✓ VERIFIED | All four classes present, all three new ones subclass `ValueError`; 14 lines (min 10). |
| `src/eacp/capabilities.py` | Two-name `Capability` Literal + `KNOWN_CAPABILITIES` frozenset | ✓ VERIFIED | `Capability = Literal["durable_approval", "inline_approval"]`; `KNOWN_CAPABILITIES` derived via `get_args`; 20 lines (min 12). Module docstring records the rejected-candidate rule verbatim as the plan required. |
| `src/eacp/policy.py` | Strict YAML loader, `Policy` schema, canonical content hash | ✓ VERIFIED | 163 lines (min 90). Exports `MAX_POLICY_BYTES`, `load_yaml_mapping`, `load_policy_file`, `Policy`, `policy_hash` — all confirmed present and behaviorally correct above. |
| `src/eacp/store.py` | `RunStore` Protocol + `SQLiteRunStore` | ✓ VERIFIED | 284 lines (min 140). `class RunStore(Protocol)` present with 6 methods; `SQLiteRunStore` type-checks against it under `mypy --strict` (whole-project run reports "Success: no issues found in 18 source files"). |
| `src/eacp/registry.py` | Entrypoint allowlist, `Workflow` schema, capability gate | ✓ VERIFIED | 128 lines (min 90). Exports `BackendType`, `Workflow`, `register_entrypoint`, `resolve_entrypoint`, `register_workflow`, `get_workflow`. Contains no import machinery (grep for `importlib`/`__import__`/`exec`/`eval`/`compile` — none found; registry reaches adapters only via `eacp.backends.load_backend_module`). |
| `src/eacp/adapters/{langgraph,crewai,ag2}_adapter.py` | Each declares its own `CAPABILITIES` | ✓ VERIFIED | langgraph: `{durable_approval, inline_approval}`; crewai: `{inline_approval}`; ag2: `{inline_approval}` — matches D-07 exactly, placed after `FRAMEWORK_VERSION` as required. |
| `tests/conftest.py` | Shared `policy_yaml` fixture | ✓ VERIFIED | 37 lines (min 20), contains `def policy_yaml`, no module-scope `eacp` import. |
| `tests/test_policy.py` | POLICY-01/02/04 executable contract | ✓ VERIFIED | 251 lines (min 130), 17 test functions, includes `test_hash_is_content_addressed`. |
| `tests/test_store.py` | TRACE-03 executable contract | ✓ VERIFIED | 234 lines (min 140), 13 test functions, includes `test_run_roundtrip`. |
| `tests/test_registry.py` | WORKFLOW-01/02/03 executable contract | ✓ VERIFIED | 220 lines (min 140), 14 test functions, includes `test_registry_has_no_import_machinery`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `src/eacp/policy.py` | `src/eacp/capabilities.py` | `from eacp.capabilities import Capability` | ✓ WIRED | Confirmed in source; `requires: list[Capability]` typed field. |
| `src/eacp/policy.py` | `src/eacp/errors.py` | `from eacp.errors import PolicyError` | ✓ WIRED | Confirmed; every loader/validation failure wraps to `PolicyError`, verified behaviorally (no bare `ValueError`/`ValidationError` leaked in spot-checks). |
| `tests/test_policy.py` | `tests/conftest.py` | `policy_yaml` fixture | ✓ WIRED | Fixture used throughout `test_policy.py`. |
| `tests/test_store.py` | `src/eacp/store.py` | `store: RunStore = SQLiteRunStore(...)` | ✓ WIRED | Confirmed via whole-project `mypy --strict` pass — this is the only mechanism that proves Protocol conformance, and it is green. |
| `src/eacp/registry.py` | `src/eacp/backends.py` | `load_backend_module(backend_type)` | ✓ WIRED | Confirmed: registry calls `load_backend_module` only inside `register_workflow`'s gate 3, at call time, not module scope. |
| `src/eacp/registry.py` | `src/eacp/capabilities.py` | `KNOWN_CAPABILITIES` | ✓ WIRED | Confirmed: `unknown = declared - KNOWN_CAPABILITIES` runtime check present. |
| `src/eacp/registry.py` | `src/eacp/policy.py` | `Policy` object in `register_workflow` signature | ✓ WIRED | Confirmed: `register_workflow(workflow: Workflow, policy: Policy)`, `policy.requires` drives the gate, `policy.policy_id` cross-checked against `workflow.policy_id`. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite | `uv run --no-sync pytest -q` | `77 passed in 1.14s` | ✓ PASS |
| Static typing (whole project) | `uv run --no-sync mypy --strict` | `Success: no issues found in 18 source files` | ✓ PASS |
| Lint (whole project) | `uv run --no-sync ruff check src tests` | `All checks passed!` | ✓ PASS |
| Lockfile integrity | `uv lock --check` | `Resolved 172 packages` (no drift) | ✓ PASS |
| SC1: unknown field rejected | ad-hoc script, `load_policy_file` on doc with `experimental_dsl_hook` | `PolicyError` naming the field | ✓ PASS |
| SC2: hash stability | ad-hoc script, two reordered/re-identified docs | identical 64-char hash; changed on content change | ✓ PASS |
| SC3: entrypoint allowlist rejection at registration | ad-hoc script, `register_workflow` with unregistered entrypoint | `ValueError` before any backend touched | ✓ PASS |
| SC4: run roundtrip, zero frameworks | ad-hoc script, confirmed `langgraph`/`crewai`/`ag2` absent via `find_spec`, then full `RunStore` roundtrip | values round-tripped exactly | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| POLICY-01 | 02-01 | Policy defined declaratively in YAML with fixed schema, loaded via hardened safe loader | ✓ SATISFIED | SC1 above; REQUIREMENTS.md marks `[x] Complete`. |
| POLICY-02 | 02-01 | Policy schema includes all six limit/tool/approval/compliance fields | ✓ SATISFIED | `Policy` model carries `max_tokens_per_run`, `max_cost_per_day`, `allowed_tools`, `forbidden_tools`, `required_approval_nodes`, `compliance_tags`, all required, no defaults (`test_every_limit_field_is_required`, 77-test suite green). |
| POLICY-04 | 02-01 | Every policy content-hashed; hash pinned to every run record and every audit log entry | **Pending (correctly)** | SC2 above satisfies "content-hashed, retrievable, stable." `store.py`'s `runs` table has `policy_hash TEXT NOT NULL`, confirming the run-record half is done. The audit-log half does not exist until Phase 4 — REQUIREMENTS.md itself marks this `Pending`, and the task prompt explicitly instructs this is a deliberately correct partial state, not a gap. Verified the NOT NULL column directly rather than trusting the claim. |
| WORKFLOW-01 | 02-03 | Workflow schema is id/name/description/backend_type/entrypoint/policy_id; entrypoint opaque, no topology fields | ✓ SATISFIED | `Workflow` model has exactly these six fields, `extra="forbid"`; `test_topology_fields_rejected` parametrized over nodes/agents/edges in the 77-test suite. |
| WORKFLOW-02 | 02-03 | Registry validates entrypoint against allowlist at registration time | ✓ SATISFIED | SC3 above. |
| WORKFLOW-03 | 02-03 | Registry fails loudly at registration if backend adapter lacks a capability the policy requires | ✓ SATISFIED | `register_workflow`'s gate 3: `missing = set(policy.requires) - declared`, raises `CapabilityError` naming workflow, missing capabilities, backend, and what it provides. Verified present and wired via source read plus the registry's own test suite (`test_capability_shortfall_rejected`) in the green 77-test run. |
| TRACE-03 | 02-02 | Run history persisted to pluggable store via Protocol, SQLite implementation for v1 | ✓ SATISFIED | SC4 above. |

No orphaned requirements: REQUIREMENTS.md's Phase 2 row set (`POLICY-01, POLICY-02, POLICY-04, WORKFLOW-01, WORKFLOW-02, WORKFLOW-03, TRACE-03`) exactly matches the union of `requirements:` fields across the three plan frontmatters.

### Anti-Patterns Found

None. Scanned all five `src/eacp/*.py` files plus `conftest.py`/`test_*.py` touched by this phase for `TBD`/`FIXME`/`XXX`, `TODO`/`HACK`/`PLACEHOLDER`, "not yet implemented"/"coming soon", and empty-return stub patterns (`return null`, `return {}`, `return []`, `=> {}`). Zero matches.

### Code Review Disposition (02-REVIEW.md / 02-REVIEW-DISPOSITION.md)

A prior code review (02-REVIEW.md) found 0 critical / 0 blocking issues, 3 warnings, 3 info items. One warning (`WR-03`, `Policy.version` had no floor) was fixed in commit `533e864`, independently confirmed present in `src/eacp/policy.py` and covered by the green test suite. The remaining two warnings (WR-01: YAML amplification within the 64KB cap; WR-02: TOCTOU window in `SQLiteRunStore.__init__`) were accepted as already-disclosed, already-scoped residuals with honest framing carried into the threat register — not re-litigated here since they were explicitly dispositioned by the human/reviewer process, not silently dropped.

## Gaps Summary

None. All four ROADMAP success criteria are behaviorally proven against the actual codebase (not SUMMARY.md claims) with independently written verification scripts run against `HEAD` (`533e864`). All three plans' artifacts exist, are substantive (well above `min_lines`), are wired together correctly, and the full 77-test suite, whole-project `mypy --strict`, `ruff check`, and `uv lock --check` all pass as of this verification run. POLICY-04's "Pending" status in REQUIREMENTS.md is intentional and independently confirmed correct (the `policy_hash NOT NULL` column exists; audit-log pinning is out of scope until Phase 4).

---

_Verified: 2026-10-02T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
