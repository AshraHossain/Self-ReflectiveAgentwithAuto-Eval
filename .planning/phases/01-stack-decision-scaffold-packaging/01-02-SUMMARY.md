---
phase: 01-stack-decision-scaffold-packaging
plan: 02
subsystem: core
tags: [lazy-import, backends, adapters, packaging, pytest, allowlist]

# Dependency graph
requires:
  - "01-01: `pyproject.toml` extras (`langgraph`/`crewai`/`ag2`), committed `uv.lock`, `[tool.pytest.ini_options]`"
  - "01-01: `src/eacp/errors.py` — `MissingExtraError`"
  - "01-01: `README.md` platform matrix (read by `test_readme_documents_the_platform_gap`)"
provides:
  - "`src/eacp/backends.py` — `_BACKENDS` allowlist, `available_backends()`, `load_backend_module()`; the package's only `importlib.import_module` site"
  - "`src/eacp/adapters/` — docstring-only package root + three placeholder adapters exposing `BACKEND` and `FRAMEWORK_VERSION`"
  - "`tests/test_packaging.py` — 5 test functions / 7 cases gating PACKAGE-01/02/04"
  - "Proven-on-real-installs evidence that `import eacp` stays framework-free with a framework present (langgraph 52-pkg env, ag2 25-pkg env)"
  - "Verbatim `uv sync --extra crewai` lancedb failure text (PACKAGE-04 evidence, Phase 6 prerequisite justification)"
affects:
  - "01-03 CI workflow — the `core` and `extra` jobs run exactly the probes this plan proved locally"
  - "Phase 2 (registry.py, Adapter Protocol) — `backends.py` naming leaves `registry.py` free"
  - "Phases 5/6/7 — each replaces its adapter placeholder body; the lazy boundary and its tests are fixed"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One lazy import site for the whole package: adapter locations are plain strings in `_BACKENDS`, resolved by `importlib.import_module` inside `load_backend_module` only"
    - "Allowlist-before-import: the `_BACKENDS` dict lookup precedes any `import_module` call, so a caller-supplied string is never interpolated into an import target (T-01-04, ASVS V5 partial)"
    - "`ModuleNotFoundError` is re-raised unchanged unless `exc.name`'s root equals the backend's declared `framework_root` — an internal adapter bug is never disguised as a missing extra (Pitfall 2, T-01-08)"
    - "Module-scope framework import inside the adapter is correct: the adapter module *is* the lazy boundary. No `try/except ImportError`, no function-body import"
    - "`FRAMEWORK_VERSION` reads `importlib.metadata.version()`, not a module `__version__` attribute, with a guarded fallback because `PackageNotFoundError` subclasses `ModuleNotFoundError`"
    - "PACKAGE-01 is asserted in a clean subprocess, never in-process: inside a pytest session another test may already have imported a framework"
    - "`autogen` gates are scoped to filenames, backend keys and `pyproject.toml` — never to raw text in `src/`, so adapter docstrings stay free to name what they are not"

key-files:
  created:
    - src/eacp/backends.py
    - src/eacp/adapters/__init__.py
    - src/eacp/adapters/langgraph_adapter.py
    - src/eacp/adapters/crewai_adapter.py
    - src/eacp/adapters/ag2_adapter.py
    - tests/__init__.py
    - tests/test_packaging.py
  modified: []

key-decisions:
  - "`FRAMEWORK_VERSION` derives from `importlib.metadata.version()` rather than 01-RESEARCH.md's `getattr(framework, '__version__', 'unknown')` — langgraph 1.2.12 exposes no `__version__` and the researched pattern silently reported `'unknown'`"
  - "The `except PackageNotFoundError` guard in each adapter is required, not defensive padding: `PackageNotFoundError` subclasses `ModuleNotFoundError`, so leaking one would make `load_backend_module` misreport an installed framework as a missing extra"
  - "Kept the version-read logic triplicated across the three placeholder adapters rather than extracting a shared helper — a helper would add an adapter→`backends` coupling and an export the plan scoped out, for 4 lines that Phases 5/6/7 rewrite anyway"
  - "Did not act on uv's own `tool.uv.required-environments` hint in the crewai failure output — Pitfall 4: it demands a wheel that does not exist and would break `uv lock` for every other platform"

patterns-established:
  - "Every new backend must be added to `_BACKENDS` to be loadable at all; there is no dynamic discovery path to bypass the allowlist"
  - "New adapters follow the placeholder shape exactly: docstring naming PyPI package / import root / install command / owning phase, `from __future__ import annotations`, one `# noqa: F401` framework import, `BACKEND`, `FRAMEWORK_VERSION`"
  - "Tests reach the package through the editable install only — no `conftest.py` path hack, no `sys.path` mutation, no `PYTHONPATH` (D-02)"

requirements-completed: [PACKAGE-01, PACKAGE-02]

# Metrics
duration: 10min
completed: 2026-09-26
---

# Phase 1 Plan 02: Lazy Backend Loader, Adapter Placeholders & Packaging Tests Summary

**The runtime half of the framework-free guarantee: one allowlist-gated `importlib.import_module` site for the whole package, three placeholder adapters, and 7 test cases that keep `import eacp` framework-free even in an environment where the frameworks are installed.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-09-26T18:40:09Z
- **Completed:** 2026-09-26T18:49:57Z
- **Tasks:** 3
- **Files modified:** 7 created, 0 modified

## Accomplishments

- `src/eacp/backends.py` is the package's **only** `importlib.import_module` site. `grep -cE '^(import|from) (langgraph|crewai|ag2)' src/eacp/backends.py` returns `0`; the module imports exactly `__future__.annotations`, `importlib`, `types.ModuleType`, and `eacp.errors.MissingExtraError`.
- `load_backend_module` has exactly three outcomes, all three demonstrated rather than asserted: a module, a `MissingExtraError` carrying the literal `pip install 'eacp[crewai]'`, or a `ValueError` for an unregistered name. A bare `ModuleNotFoundError` for a missing framework is not reachable.
- **Pitfall 2 verified by construction, not by reading.** An adapter with a genuine bad internal import (`from eacp.does_not_exist import Nope`, registered through a scratch `_BACKENDS` entry so no repo file was polluted) propagated `ModuleNotFoundError: eacp.does_not_exist` untouched. A real defect cannot hide behind "install the extra".
- PACKAGE-01 proven in the only environments where it is meaningful — **with the framework installed.** In the 52-package `eacp[langgraph]` env and the 25-package `eacp[ag2]` env, `import eacp` left `sys.modules` free of all three framework roots, then `load_backend_module(...)` loaded the adapter and reported a real framework version.
- `uv run pytest -q`: **7 passed in 0.20s** (4 plain + 3 parametrized) against 01-VALIDATION.md's 2-second budget — a 10× margin, which matters because this is the per-task sampling command for the rest of the phase.
- Package counts reproduced 01-RESEARCH.md exactly: core **17**, `eacp[ag2]` **25**, `eacp[langgraph]` **52**. No drift, so nothing leaked into core.
- The CrewAI gap was confirmed deliberately and its verbatim error captured, de-risking plan 01-03's never-yet-executed CI run and justifying Phase 6's Docker/colima prerequisite.

## Task Commits

1. **Task 1: Lazy backend loader + three placeholder adapters** — `679a9ee` (feat)
2. **Task 2: `tests/test_packaging.py` and a green suite** — `bda2cf1` (test)
3. **Task 3: Realize each extra locally** (verification-only task; carries the Rule 1 fix it uncovered) — `ee230b3` (fix)

## Files Created/Modified

- `src/eacp/backends.py` — `_BACKENDS: dict[str, tuple[str, str, str]]` with three entries (backend name → adapter module path, extra name, framework root), `available_backends()` returning `('langgraph', 'crewai', 'ag2')`, and `load_backend_module()`. Allowlist lookup runs **before** any import; `raise ... from None` on the `KeyError` so the traceback stays clean.
- `src/eacp/adapters/__init__.py` — docstring only, zero import statements, addressed to the Phase 5/6/7 author who will be thinking about ergonomics rather than PACKAGE-01.
- `src/eacp/adapters/langgraph_adapter.py` — placeholder; `BACKEND = "langgraph"`, `FRAMEWORK_VERSION` → `1.2.12`. Real logic Phase 5.
- `src/eacp/adapters/crewai_adapter.py` — placeholder; `BACKEND = "crewai"`. Docstring notes the macOS x86_64 platform gap. Real logic Phase 6.
- `src/eacp/adapters/ag2_adapter.py` — placeholder; `BACKEND = "ag2"`, `FRAMEWORK_VERSION` → `1.1.0`. Docstring deliberately names `autogen` / `pyautogen` / `autogen-agentchat` as what this adapter is **not**.
- `tests/__init__.py` — empty.
- `tests/test_packaging.py` — five test functions, no `conftest.py`, no `sys.path`/`PYTHONPATH` reference.

## Measurements (plan `<output>` requirements)

### Package counts

| Environment | Command | Packages | 01-RESEARCH.md |
|---|---|---|---|
| core | `uv sync --locked --no-default-groups` | **17** | 17 ✅ |
| `eacp[ag2]` | `… --extra ag2` | **25** | 25 ✅ |
| `eacp[langgraph]` | `… --extra langgraph` | **52** | 52 ✅ |

### Observed `FRAMEWORK_VERSION`

| Backend | Reported | 01-RESEARCH.md measured |
|---|---|---|
| `langgraph` | **1.2.12** | 1.2.12 ✅ |
| `ag2` | **1.1.0** | 1.1.0 ✅ |
| `crewai` | not measurable on this host | — |

### `uv run pytest -q` wall time

**0.20 s** for 7 tests (0.28 s and 0.45 s on two later runs), against 01-VALIDATION.md's **2 s** budget. `ruff check src tests` also clean.

### Verbatim `uv sync --locked --no-default-groups --extra crewai` failure (host: `x86_64 Darwin`)

```
Resolved 172 packages in 25ms
error: Distribution `lancedb==0.30.0 @ registry+https://pypi.org/simple` can't be installed because it doesn't have a source distribution or wheel for the current platform

hint: You're on macOS (`macosx_26_0_x86_64`), but `lancedb` (v0.30.0) only has wheels for the following platforms: `manylinux_2_17_aarch64`, `manylinux_2_17_x86_64`, `manylinux_2_28_aarch64`, `manylinux_2_28_x86_64`, `manylinux2014_aarch64`, `manylinux2014_x86_64`, `macosx_11_0_arm64`, `win_amd64`; consider adding "sys_platform == 'darwin' and platform_machine == 'x86_64'" to `tool.uv.required-environments` to ensure uv resolves to a version with compatible wheels
```

Two things worth carrying forward:

1. **`Resolved 172 packages` precedes the error.** Locking succeeded; only *installing* failed. This is 01-RESEARCH.md Pitfall 4 confirmed live — lock-time and install-time resolution are different operations, and PACKAGE-03 was never at risk on this host.
2. **uv's own hint is the wrong advice** and the plan pre-emptively forbade it. `tool.uv.required-environments` *demands* a wheel that does not exist; adding it would break `uv lock` for every platform to fix none. `pyproject.toml` still has no `[tool.uv]` table and `crewai>=1.15,<2` is intact (both grep-verified).

## Decisions Made

- **`importlib.metadata.version()` replaced the researched `getattr(framework, "__version__", …)` pattern** in all three adapters. See Deviations for the discovery; the decision itself is that distribution metadata is the authoritative version source and needs no per-framework special-casing, whereas module attributes are a per-framework convention langgraph does not follow.
- **Kept the 4-line version-read triplicated across three placeholders** instead of extracting a helper. A helper's natural home is `backends.py`, which would add an adapter→`backends` import coupling and a fourth export the plan's artifact contract does not list — a worse trade for code that Phases 5/6/7 rewrite.
- **Probed Pitfall 2 through a scratch-directory module plus a runtime `_BACKENDS` injection** rather than temporarily breaking a real adapter. Same evidence, zero risk of committing a broken import.
- **Ran every probe under `uv run --no-sync`** (venv-scoped) so this machine's stale global `crewai 1.9.3` could not produce a false green — T-01-09. A bare `python -c "import crewai"` would have.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `langgraph` adapter reported `FRAMEWORK_VERSION == "unknown"`**

- **Found during:** Task 3, first probe run (`AssertionError: langgraph adapter could not read a framework version`)
- **Issue:** 01-RESEARCH.md §Pattern 3 prescribes `FRAMEWORK_VERSION = getattr(<framework>, "__version__", "unknown")` and the plan reproduces it verbatim for all three adapters. It works for `ag2` (1.1.0) but **langgraph 1.2.12 exposes no module-level `__version__`** — verified directly: `hasattr(langgraph, "__version__")` is `False` and no attribute containing "version" exists on the module. The `"unknown"` fallback swallowed this silently, and the plan's own acceptance criterion (`FRAMEWORK_VERSION` must not be `"unknown"`) caught it. Research measured langgraph at 1.2.12 by some other route and the pattern was never cross-checked against it.
- **Root cause, not symptom:** fixed in all three adapters, not only langgraph. The `getattr` pattern is wrong for every adapter — it happens to work for `ag2` and `crewai` today, which is exactly how this regresses again when a framework drops the attribute in a minor bump.
- **Fix:** `FRAMEWORK_VERSION = importlib.metadata.version("<dist>")`, guarded by `except importlib.metadata.PackageNotFoundError` falling back to the old `getattr`. **The guard is load-bearing, not padding:** `PackageNotFoundError` subclasses `ModuleNotFoundError` (verified), so an uncaught one raised at adapter module scope would be caught by `load_backend_module`'s handler, match the backend's `framework_root`, and report "install the extra" for a framework that *is* installed — Pitfall 2 / T-01-08 arriving from a direction neither the research nor the plan anticipated.
- **Files modified:** `src/eacp/adapters/langgraph_adapter.py`, `src/eacp/adapters/crewai_adapter.py`, `src/eacp/adapters/ag2_adapter.py`
- **Verification:** `langgraph` → `1.2.12`, `ag2` → `1.1.0`, both matching 01-RESEARCH.md's measured values; Task 1's grep gates re-run clean; `ruff check` clean
- **Committed in:** `ee230b3`

---

**Total deviations:** 1 auto-fixed (1 bug). No architectural change, no `Rule 4` escalation, no dependency added.
**Impact on plan:** All three adapters gained 4 lines each and one stdlib import. File set, exports, allowlist, and every gate are unchanged from the plan.

## Issues Encountered

- **The flagged research-vs-grep conflict did not recur, because the plan pre-empted it.** 01-01 hit a docstring containing `import langgraph` tripping an anti-regression grep. This plan's adapters contain *real* `import langgraph` / `import crewai` / `import ag2` lines by design, and the plan correctly scoped every gate accordingly: the framework-import grep targets `backends.py` and `adapters/__init__.py` only, and the `autogen` gate is filesystem-scoped (`ls src/eacp/adapters | grep -i autogen`) rather than a text search — so `ag2_adapter.py`'s docstring naming `autogen`/`pyautogen`/`autogen-agentchat` as what it is not passes cleanly. No grep needed waiving.
- **`eacp[crewai]` remains uninstallable on this host**, as expected and pre-decided. Not a defect; evidence captured above. No workaround attempted.
- **`set -e` did not abort the Task 3 loop** on the first langgraph assertion failure (the loop body continued to `ag2`). Cosmetic — the failure was visible and acted on — but worth knowing if plan 01-03 reuses that loop shape in CI, where a silently-continuing loop could mask a red cell.

## Threat Flags

None. This plan introduced no network endpoint, auth path, or schema at a trust boundary. It **implements** the mitigations the plan's `<threat_model>` registered:

| Threat ID | Disposition | Delivered as |
|---|---|---|
| T-01-04 | mitigate | `_BACKENDS` lookup precedes every `import_module`; `load_backend_module("autogen")` → `ValueError`, kept gated by `test_unknown_backend_is_a_value_error` |
| T-01-05 | mitigate | `MissingExtraError` text is built from the framework root and extra name only — no path, no env var, no venv location |
| T-01-08 | mitigate | `if (exc.name or "").split(".")[0] != framework_root: raise`, demonstrated with a genuinely broken adapter import. Extended during this plan to cover `PackageNotFoundError` (see Deviations) |
| T-01-01 | mitigate | `ag2_adapter.py` filename, `"ag2"` backend key, filesystem-scoped `test_no_adapter_is_named_autogen` |
| T-01-09 | mitigate | Every probe ran under `uv run --no-sync`; the stale global `crewai 1.9.3` was never consulted |
| T-01-10 | accept | `langgraph` and `ag2` imported and executed at adapter load; both `[OK]` in the 01-RESEARCH.md legitimacy audit and hash-verified from `uv.lock` |
| T-01-SC | mitigate | Every install used `uv sync --locked` against the committed hash-pinned lock; `uv lock --check` still exits 0. **`slopcheck install` was not run** (and must never be) |

## Known Stubs

Three, all **intentional and phase-scoped** — they are the plan's named deliverable, not unfinished work:

| Stub | File | Resolved by |
|---|---|---|
| `langgraph_adapter` — `BACKEND` + `FRAMEWORK_VERSION` only, no adapter logic | `src/eacp/adapters/langgraph_adapter.py` | Phase 5 (LANGGRAPH-01, LANGGRAPH-02) |
| `crewai_adapter` — same | `src/eacp/adapters/crewai_adapter.py` | Phase 6 (CREWAI-01/02/03) |
| `ag2_adapter` — same | `src/eacp/adapters/ag2_adapter.py` | Phase 7 (AG2-01, AG2-02) |

Each carries its owning phase and requirement IDs in its own docstring. The plan's goal — proving the extra resolves and the lazy boundary holds — is fully achieved by the placeholder form; a fuller body would be Phase 2+ scope creep (Pitfall 7).

Nothing in `backends.py` or `tests/test_packaging.py` is a stub.

## User Setup Required

None.

## Next Phase Readiness

**Ready for plan 01-03** (`.github/workflows/ci.yml`, jobs `core` and `extra`):

- Every assertion the CI jobs need has now been executed locally and passed, except the `eacp[crewai]` cell. The `core` job's `find_spec` probe, the `extra` job's leak-then-load probe, `uv lock --check`, and `uv run pytest -q` are all verified working with the exact flag combinations 01-RESEARCH.md §Pattern 4 prescribes.
- The `extra` job's `EACP_EXTRA` env var maps directly onto the probe shape used here (`EACP_EXTRA="$x" uv run --no-sync --no-default-groups python -c …`), so the workflow can lift it verbatim.
- `macos-latest` is arm64, so the CrewAI cell that cannot run here should pass there. That cell and `ubuntu-latest` are the **only** untested paths in the phase.

**Carried concerns:**

- `UV_VERSION` in 01-03 must be exactly `0.12.19` — the lock is `revision = 3` and a version mismatch can redden `uv lock --check` on format alone.
- 01-RESEARCH.md Pitfall 6 (`macos-latest` silently repointing to Intel) deserves the `uname -m` guard in the workflow: this plan produced the exact error text such a guard converts into a legible message.
- Phase 6 still needs the already-decided Docker/colima Linux container; today's captured `lancedb` error is the documentation for why.
- `prompt.md` remains untracked at the repo root despite `PROJECT.md` and `CLAUDE.md` citing it as authoritative. Pre-existing, out of scope, still in `deferred-items.md`.

## Self-Check: PASSED

- All 7 claimed artifacts exist on disk (`backends.py`, 4 files under `src/eacp/adapters/`, `tests/__init__.py`, `tests/test_packaging.py`).
- All 3 task commits exist in git: `679a9ee`, `bda2cf1`, `ee230b3`.
- Plan `<verification>` steps 1-8 all pass: `7 passed`, `uv lock --check` exit 0, `('langgraph', 'crewai', 'ag2')`, grep gates `0` and `0`, no `autogen` filename, `src/eacp/registry.py` absent.
- No file deletions in any commit (`git diff --diff-filter=D HEAD~1 HEAD` empty).

---
*Phase: 01-stack-decision-scaffold-packaging*
*Completed: 2026-09-26*
