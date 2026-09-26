---
phase: 1
slug: stack-decision-scaffold-packaging
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-09-25
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 (+ pytest-asyncio 1.4.0) |
| **Config file** | none — greenfield; Wave 0 creates `[tool.pytest.ini_options]` in `pyproject.toml` |
| **Quick run command** | `uv run pytest -q` |
| **Full suite command** | `uv run pytest -q` (identical to quick run in this phase — diverges from Phase 5 onward when marker-gated adapter tests appear) |
| **Estimated runtime** | < 2 seconds (no framework imports in this phase) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q`
- **After every plan wave:** Run `uv run pytest -q` + `uv lock --check`
- **Before `/gsd-verify-work`:** All 8 CI matrix jobs (core × 2 OS, 3 extras × 2 OS) must be green
- **Max feedback latency:** 2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 0 | PACKAGE-01 | V5 (partial) | `import eacp` pulls no framework into `sys.modules`, in any env | unit (clean subprocess) | `uv run pytest tests/test_packaging.py::test_import_eacp_does_not_import_any_framework -x` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 0 | PACKAGE-01 | V14 | core install *contains* no framework package | CI env assertion | `uv sync --locked --no-default-groups && uv run --no-sync --no-default-groups python -c "import importlib.util as u,eacp; assert not [m for m in ('langgraph','crewai','ag2') if u.find_spec(m)]"` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 0 | PACKAGE-02 | V5 | each backend loads, or raises `MissingExtraError` naming its extra | unit (parametrized) | `uv run pytest tests/test_packaging.py::test_backend_either_loads_or_explains_itself -x` | ❌ W0 | ⬜ pending |
| 01-01-04 | 01 | 0 | PACKAGE-02 | — | each extra actually installs and imports | integration (CI matrix) | `uv sync --locked --no-default-groups --extra {langgraph,crewai,ag2}` + loader probe | ❌ W0 | ⬜ pending |
| 01-01-05 | 01 | 0 | PACKAGE-02 | Tampering (typosquat) | no module/extra named `autogen` anywhere | unit (filesystem) | `uv run pytest tests/test_packaging.py::test_no_adapter_is_named_autogen -x` | ❌ W0 | ⬜ pending |
| 01-01-06 | 01 | 0 | PACKAGE-03 | V14 | lockfile committed and in sync with `pyproject.toml` | CI gate | `uv lock --check` | ❌ W0 | ⬜ pending |
| 01-01-07 | 01 | 0 | PACKAGE-04 | — | README documents the platform matrix incl. macOS x86_64 / lancedb gap | unit (content) | `uv run pytest tests/test_packaging.py::test_readme_documents_the_platform_gap -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Planner assigns real task IDs during PLAN.md creation — the IDs above are provisional, mapped 1:1 to 01-RESEARCH.md's "Phase requirements → test map".*

---

## Wave 0 Requirements

- [ ] `[tool.pytest.ini_options]` block in `pyproject.toml` — no test config exists yet (covers all four requirements)
- [ ] `[dependency-groups] dev` with `pytest>=9.1`, `pytest-asyncio>=1.4` — test framework not yet a dependency
- [ ] `tests/__init__.py`
- [ ] `tests/test_packaging.py` — the six automated tests above (stubs first, since the module under test doesn't exist yet)
- [ ] `.github/workflows/ci.yml` — CI-level assertions for PACKAGE-01/02/03

**Ordering constraint (from research):** `tests/test_packaging.py` imports `eacp.backends`, so it cannot pass before `backends.py` and the adapter placeholders exist — Wave 0 creates config + empty test module; the real tests land in the same wave as the code they guard. `test_readme_documents_the_platform_gap` will fail until README.md exists — sequence README before that test, or accept one red wave transiently.

---

## Manual-Only Verifications

*None — all four phase requirements (PACKAGE-01 through PACKAGE-04) have automated verification. PACKAGE-04 would normally be "docs, verify by eye," but a content-presence test on the README makes it a real automated gate — the platform matrix is exactly the kind of doc that silently rots without one.*

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 2s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
