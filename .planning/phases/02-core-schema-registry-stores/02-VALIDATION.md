---
phase: "2"
slug: "core-schema-registry-stores"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-27"
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `02-RESEARCH.md` §Validation Architecture, whose claims were executed
> against the project venv rather than recalled.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` 9.1.1 (+ `pytest-asyncio` 1.4.0, unused this phase — nothing async in Phase 2 per D-06) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths=["tests"]`, `asyncio_mode="auto"`, `--strict-markers` |
| **Quick run command** | `uv run --no-sync pytest -q tests/test_policy.py tests/test_registry.py tests/test_store.py` |
| **Full suite command** | `uv run pytest -q && uv run mypy --strict && uv run ruff check` |
| **Estimated runtime** | ~1 s (Phase 1's 7 tests run in 0.06 s; budget from 01-VALIDATION.md is 2 s) |
| **Existing coverage** | `tests/test_packaging.py` (Phase 1, 7 tests) — **do not modify** |

---

## Sampling Rate

- **After every task commit:** `uv run --no-sync pytest -q <the task's test file>` **and** `uv run --no-sync mypy --strict`
- **After every plan wave:** `uv run pytest -q && uv run mypy --strict && uv run ruff check`
- **Before `/gsd-verify-work`:** full suite green
- **Max feedback latency:** ~2 seconds

`mypy --strict` is part of per-task sampling, not just the wave gate, because it is the
**only** mechanism that verifies `SQLiteRunStore` actually satisfies the `RunStore`
Protocol — `@runtime_checkable` is signature-blind and was verified returning `True` for
a class with entirely wrong arities (02-RESEARCH.md §Findings).

---

## Per-Requirement Verification Map

Task IDs are assigned by the planner; this map is the requirement→test contract the
plans must satisfy.

| Requirement | Behavior verified | Threat Ref | Test Type | Automated Command | File |
|---|---|---|---|---|---|
| POLICY-01 | Unknown field rejected at load | — | unit | `pytest tests/test_policy.py::test_unknown_field_rejected` | ❌ W0 |
| POLICY-01 | Non-mapping root / empty file rejected | — | unit | `…::test_non_mapping_root_rejected` | ❌ W0 |
| POLICY-01 | **Duplicate key rejected** | T-02-01 | unit | `…::test_duplicate_key_rejected` | ❌ W0 |
| POLICY-01 | `!!python/` tag rejected | — | unit | `…::test_python_tag_rejected` | ❌ W0 |
| POLICY-01 | Oversized document rejected | T-02-02 | unit | `…::test_oversized_document_rejected` | ❌ W0 |
| POLICY-02 | All limit fields required, no defaults | — | unit | `…::test_every_limit_field_is_required` (parametrized) | ❌ W0 |
| POLICY-02 | YAML `yes` rejected for an int field | — | unit | `…::test_yaml_bool_rejected_for_int_limit` | ❌ W0 |
| POLICY-04 | Hash stable across key order, list order, `policy_id`, `version`, `25.00`/`25.0` | — | unit | `…::test_hash_is_content_addressed` | ❌ W0 |
| POLICY-04 | Changing any limit changes the hash | — | unit | `…::test_hash_changes_when_a_limit_changes` (parametrized) | ❌ W0 |
| POLICY-04 | **Hashed key set is pinned** (drift guard) | — | unit | `…::test_hashed_key_set_is_pinned` | ❌ W0 |
| WORKFLOW-01 | Schema rejects `nodes`/`agents`/`edges` | — | unit | `pytest tests/test_registry.py::test_topology_fields_rejected` | ❌ W0 |
| WORKFLOW-01 | `BackendType` Literal matches `available_backends()` | — | unit | `…::test_backend_literal_matches_backends_module` | ❌ W0 |
| WORKFLOW-02 | Unknown entrypoint rejected at **registration** | — | unit | `…::test_unregistered_entrypoint_rejected` | ❌ W0 |
| WORKFLOW-02 | Malformed name rejected by charset | — | unit | `…::test_entrypoint_name_charset` (parametrized: `os.system`, `../etc`, `A`, `""`) | ❌ W0 |
| WORKFLOW-02 | Re-registration raises rather than overwrites | T-02-05 | unit | `…::test_duplicate_entrypoint_registration_rejected` | ❌ W0 |
| WORKFLOW-02 | `registry.py` contains **zero** `importlib` calls | T-02-04 | unit (AST) | `…::test_registry_has_no_import_machinery` | ❌ W0 |
| WORKFLOW-03 | Capability shortfall raises `CapabilityError` | — | unit | `…::test_capability_shortfall_rejected` (monkeypatched fake module — no extra needed) | ❌ W0 |
| WORKFLOW-03 | Unknown capability in `requires:` rejected at load | — | unit | `tests/test_policy.py::test_unknown_capability_rejected` | ❌ W0 |
| TRACE-03 | Write run → steps → finish → read back | — | integration | `pytest tests/test_store.py::test_run_roundtrip` | ❌ W0 |
| TRACE-03 | `list_runs` filters by workflow and `since` | — | integration | `…::test_list_runs_filters` | ❌ W0 |
| TRACE-03 | `SQLiteRunStore` satisfies `RunStore` | — | **static** | `uv run mypy --strict` | ❌ W0 |
| TRACE-03 | Cross-thread call succeeds (CrewAI runs on threads) | — | integration | `…::test_store_is_thread_safe` | ❌ W0 |
| TRACE-03 | Orphan step rejected (FK enforced) | — | integration | `…::test_orphan_step_rejected` | ❌ W0 |
| TRACE-03 | Value with SQL metacharacters is inert | T-02-\<tbd\> | integration | `…::test_filter_value_is_parameterized` | ❌ W0 |
| Success criterion 4 | Zero framework code imported | — | unit + CI | `tests/test_packaging.py` + CI `core` job | ✅ exists |

*Status legend: ⬜ pending · ✅ green · ❌ red · W0 = created in Wave 0*

---

## Wave 0 Requirements

- [ ] `tests/test_policy.py` — POLICY-01, POLICY-02, POLICY-04
- [ ] `tests/test_registry.py` — WORKFLOW-01, WORKFLOW-02, WORKFLOW-03
- [ ] `tests/test_store.py` — TRACE-03
- [ ] `tests/conftest.py` — one `policy_yaml` fixture and one `store` fixture on `tmp_path`
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` += `filterwarnings = ["error::DeprecationWarning"]`

**No framework install needed. No CI change needed.** Phase 2 adds zero dependencies;
the `core` job already runs `uv sync --locked --no-default-groups` then `pytest -q` with
no extras, which is exactly what success criterion 4 requires.

### Two Wave 0 items that are load-bearing, not hygiene

1. **`filterwarnings = ["error::DeprecationWarning"]`** — Python 3.12 deprecated the
   default `sqlite3` datetime adapter. Without this line the deprecation is a silent
   warning and the pitfall can be reintroduced by any later phase; with it, reintroduction
   is a test failure.
2. **`tmp_path`, never `:memory:`** — verified: under connection-per-call (D-13's store
   design), a second connection to `:memory:` reports `no such table`. A suite written
   against `:memory:` would fail for reasons unrelated to the code under test.

---

## Manual-Only Verifications

None. Every Phase 2 requirement is machine-verifiable — there is no UI, no network
surface, and no human-judgment criterion in this phase. The `/gsd-verify-work` pass
should therefore be fully programmatic, as Phase 1's was.
