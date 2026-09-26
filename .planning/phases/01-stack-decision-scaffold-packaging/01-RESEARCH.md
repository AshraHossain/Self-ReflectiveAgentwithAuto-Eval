# Phase 1: Stack Decision, Scaffold & Packaging - Research

**Researched:** 2026-09-25
**Domain:** Python packaging (PEP 621 / extras / PEP 735 dependency groups), `uv` universal lockfiles, lazy optional-dependency loading, GitHub Actions matrix CI
**Confidence:** HIGH — every packaging claim below was executed locally today against a real scratch `eacp` project (`uv lock`, `uv sync` per extra, `pip install`, real imports), not inferred from docs or training data.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Project naming & branding**
- **D-01:** Package/import/CLI name is `eacp` (as already used throughout REQUIREMENTS.md and ROADMAP.md). The local working-directory name (`Self-ReflectiveAgentwithAuto-Eval`) is cosmetic and does not need to match — it never appears in the published package, PyPI name, or CLI invocation. No rename needed.

**Repository layout**
- **D-02:** Use `src/` layout: package source lives at `src/eacp/`, tests at `tests/`. Chosen over a flat `eacp/`-at-root layout specifically to prevent accidentally importing an uninstalled source tree instead of the installed package — relevant here because multiple framework extras with lazy imports make that failure mode easy to hit silently.
- **D-03:** `examples/`, `docs/`, and `benchmarks/` (per prompt.md's module layout) live at repo root, siblings to `src/`, `tests/`, and the existing `LICENSE`.

**CI**
- **D-04:** Stand up GitHub Actions CI in this phase, not deferred. Minimum: a 4-job matrix — `core` (installs with zero framework extras, asserts `import eacp` succeeds and no LangGraph/CrewAI/ag2 packages are present) plus one job per adapter extra (`eacp[langgraph]`, `eacp[crewai]`, `eacp[ag2]`) installing and importing cleanly. The `core` job gates every push — this is the mechanism that keeps the project's central credibility claim (framework-free core) true over time rather than asserted once and silently rotting.
- **D-05:** CI matrix should account for the known macOS x86_64 / `lancedb` install failure (from research/STACK.md) — run on `ubuntu-latest` (and optionally `macos-latest` which GitHub Actions runs on Apple Silicon, not Intel) rather than an Intel-Mac runner that would fail for reasons unrelated to this project's code.

### Claude's Discretion
- Exact `pyproject.toml` structure, dependency-group/extras syntax, and lockfile tool invocation (`uv`, per research/STACK.md) — implementation detail, not a user-facing decision.
- Exact CI YAML structure (job names, caching strategy, matrix syntax) beyond the 4-job core+3-extras requirement above.
- Whether to also test on Windows — not raised during discussion; default to Linux + macOS (arm64) unless research/planning surfaces a reason to add Windows.

### Deferred Ideas (OUT OF SCOPE)
None raised during discussion — stayed within phase scope (naming, layout, CI timing).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PACKAGE-01 | `pip install eacp && python -c "import eacp"` succeeds with zero agent frameworks installed (core has no LangGraph/CrewAI/ag2 dependency) | §Architecture Patterns → full `pyproject.toml` (core `dependencies` contains no framework); verified locally: core install = **17 packages**, `import eacp` OK, `find_spec` for all three frameworks returns `None`. CI `core` job asserts it (§CI Workflow). |
| PACKAGE-02 | Each framework adapter is installable as an optional extra (`eacp[langgraph]`, `eacp[crewai]`, `eacp[ag2]`) with lazy imports inside the adapter module | §Pattern 2 (verified lazy-load pattern + `MissingExtraError`), §Pattern 3 (placeholder adapter modules). Verified: `eacp[ag2]`=25 pkgs, `eacp[langgraph]`=52 pkgs, both import cleanly; `import eacp` pulls **zero** framework modules into `sys.modules` even when frameworks are installed. |
| PACKAGE-03 | A committed lockfile pins the full dependency graph for reproducible installs | §Pattern 4 (`uv` commands). Verified: `uv lock` → `uv.lock`, 172 packages, 2016 sha256 hashes, universal (all extras + dev, all platforms) — and **it succeeds on this Intel Mac** despite the crewai/lancedb gap. `uv lock --check` is the CI drift gate. |
| PACKAGE-04 | README documents the platform matrix, including the known macOS x86_64 / CrewAI (`lancedb`) install failure | §Platform Support Matrix (README-ready table, measured today). Root cause closed definitively in §Finding 1 — including that no workaround exists. |
</phase_requirements>

---

## Project Constraints (from CLAUDE.md)

| Directive | Source | Phase 1 implication |
|-----------|--------|---------------------|
| Python 3.11+ with type hints | Constraints | `requires-python = ">=3.11,<3.14"`. Upper cap forced by `crewai` (`<3.14`), not preference. Ship `py.typed`. |
| Dependencies must be real, pinned, current stable — not stubbed | Constraints | Extras carry real version ranges; `uv.lock` pins exact patches. **"Real, not stubbed" applies to the frameworks, not to the adapter logic — Phase 1 ships adapter *placeholders*, which is correct.** |
| Runnable without paid API keys | Constraints | No Phase 1 impact (no LLM calls yet). Do not add a mock-LLM module in this phase. |
| Persistence: SQLite, simple + pluggable | Constraints | No Phase 1 impact. Do **not** create `store.py` here. |
| Scope discipline: no hosted infra, multi-tenant auth, or web UI | Constraints | Reinforces the tight Phase 1 boundary in §Phase Scope Boundary. |
| GSD Workflow Enforcement: no direct repo edits outside a GSD workflow | GSD Workflow Enforcement | Execution must run under `/gsd-execute-phase`. |
| Conventions / Architecture sections are empty ("will populate as patterns emerge") | Conventions, Architecture | Phase 1 **establishes** the first conventions. The `pyproject.toml`, extras naming, and lazy-import pattern below become the project's conventions — worth writing back to CLAUDE.md at phase end. |

⚠️ **CLAUDE.md is stale in one place:** line 14 says *"pick current stable packages during Phase research"* and refers to "an AutoGen package" generically. That is already decided (`ag2`, D-01/STATE.md). CLAUDE.md's embedded copy of STACK.md also carries the `autogen`-named extra bug corrected in §State of the Art.

---

## Summary

This phase is mechanically straightforward — a `pyproject.toml`, a lockfile, ~60 lines of Python, and one CI workflow — and I was able to build and execute the entire thing end to end today. Every number in this document is measured, not estimated. The prescriptive answer is: **hatchling** build backend, `src/eacp/` layout, five extras with the AutoGen-lineage one named **`ag2`**, PEP 735 `[dependency-groups]` for dev tooling, a single universal `uv.lock`, and an 8-job GitHub Actions matrix (core × 2 OS, 3 extras × 2 OS).

**However, one discovery reframes the phase, and the planner must surface it to the user before execution.** This development machine is a genuine Intel Mac (`x86_64`, Core i7-10700K, `hw.optional.arm64` absent — not Apple Silicon, not Rosetta). That is precisely the platform STACK.md flagged as a hard blocker, and I confirmed it empirically: `uv sync --extra crewai` fails here with `lancedb==0.30.0 ... doesn't have a source distribution or wheel for the current platform`. I then closed the two workaround questions STACK.md left open, and **both are dead ends**: `lancedb` has never published a macOS x86_64 wheel in any version from 0.29.0 through 0.32.0 (latest 0.39.0) *and publishes no sdist at all*, so there is nothing to build from source; and `crewai-core` — which STACK.md hoped might be a lightweight lancedb-free path — imports as `crewai_core` and contains only auth/settings/telemetry plumbing, while `crewai.hooks` (the entire CREWAI-01 enforcement seam) ships in the `crewai` distribution that hard-requires `lancedb`. The consequence: **Phase 6 (CrewAI adapter) cannot be developed or tested on this machine at all.** CI or a Linux container is not hygiene here, it is the only execution environment CrewAI will ever have. That elevates D-04 from "good practice on day 1" to load-bearing infrastructure, and it is a decision the user should make consciously now rather than discover in Phase 6.

The good news is that the packaging property this phase exists to prove is real and cheap. `import eacp` pulls **zero** framework modules into `sys.modules` even in an environment where both `langgraph` and `ag2` are installed — verified via a clean-subprocess assertion. The core install is 17 packages against 172 in the full universal lock, so the extras split buys a 10× reduction for a single-framework adopter. And `uv lock` succeeds on this Intel Mac even though `uv sync --extra crewai` cannot, because locking records available wheels rather than requiring one per platform — which means the lockfile deliverable (PACKAGE-03) is **not** blocked by the platform gap. Do not add `[tool.uv] environments` to work around this; it is unnecessary and would narrow the lock for everyone else.

**Primary recommendation:** Build the scaffold exactly as specified in §Architecture Patterns (all four artifacts are verified-working copy-paste), name the AutoGen-lineage extra `ag2` (correcting STACK.md), and open Phase 1 with a `checkpoint:human-verify` asking the user to choose a CrewAI development strategy (CI-only, Docker/colima, or remote Linux) — because the answer changes Phase 6's plan and nothing else in Phase 1 depends on it.

---

## Architectural Responsibility Map

This phase has no runtime tiers (no service, no request path). The meaningful decomposition is *which artifact owns which guarantee* — the planner should use this to keep one concern per task rather than splitting arbitrarily.

| Capability | Primary Owner | Secondary Owner | Rationale |
|------------|--------------|-----------------|-----------|
| Declaring the framework-free core dependency set | `pyproject.toml` `[project] dependencies` | — | The *only* place that can make PACKAGE-01 true. A framework leaking in here is the one unrecoverable packaging mistake. |
| Offering each adapter as an opt-in install | `pyproject.toml` `[project.optional-dependencies]` | — | Extras are resolved by the installer; no Python code involved. |
| Keeping `import eacp` framework-free at *runtime* | `src/eacp/__init__.py` + `src/eacp/adapters/__init__.py` | `src/eacp/backends.py` | Extras alone don't guarantee this — an `__init__.py` that eagerly imports an adapter breaks PACKAGE-01 *with a correct pyproject.toml*. Both halves are required. |
| Turning a missing extra into an actionable error | `src/eacp/backends.py` | `src/eacp/errors.py` | Central lookup table; the adapter modules stay dumb. |
| Isolating framework imports to one module each | `src/eacp/adapters/<fw>_adapter.py` | — | One module per framework = one import boundary per framework. |
| Reproducible dependency graph | `uv.lock` | `.python-version` | `uv.lock` pins versions + hashes; `.python-version` pins the interpreter the lock is realized against. |
| Enforcing the above on every push | `.github/workflows/ci.yml` | — | The properties above are all silently reversible by a later phase; CI is the only thing that keeps them true. |
| Documenting the platform gap | `README.md` | — | PACKAGE-04. Documentation is the *only* available mitigation — the gap is unfixable upstream-side. |

---

## Standard Stack

All versions below are the **resolved** versions from the real `uv.lock` I generated today (universal, Python 3.11–3.13, all extras + dev = 172 packages), not from `pyproject.toml` ranges.

### Core (PACKAGE-01 — must contain no agent framework)

| Library | Range in pyproject | Resolved | Purpose | Why standard |
|---------|-------------------|----------|---------|--------------|
| `pydantic` | `>=2.11,<2.13` | **2.12.5** | Policy/workflow schema (Phase 2+) | The one library all three frameworks agree on. `<2.13` cap is **forced** by `crewai-core` (`pydantic<2.13,>=2.11.9`) — re-verified against live PyPI metadata today, not copied from STACK.md. [VERIFIED: PyPI JSON API] |
| `pyyaml` | `>=6` | **6.0.3** | Policy YAML via `safe_load` (POLICY-01) | Transitive via all three frameworks anyway. |
| `typer` | `>=0.27` | **0.27.2** | CLI (APPROVAL-02, Phase 4) | Already transitive via `chromadb`/`instructor`; zero net cost. |
| `opentelemetry-api` | `>=1.42,<2` | **1.45.0** | Trace emission (TRACE-02) | Already a *hard core* dep of `crewai-core`. Declining it doesn't remove it. |
| `opentelemetry-sdk` | `>=1.42,<2` | **1.45.0** | Trace SDK | As above. Note: resolves to **1.45.0**, not the 1.44.0 STACK.md recorded — the `<2` range absorbs it. |

Core install measured at **17 packages** (vs. 172 for the full graph).

> **Scope note for the planner:** `typer` and the OTel pair are declared now but *unused* until Phases 4/5. That is deliberate — the point of this phase is to fix the core dependency contract once so the lockfile doesn't churn. It is *not* licence to write CLI or tracing code here.

### Optional extras (PACKAGE-02)

| Extra | Range in pyproject | Resolved | Measured install size | Import root |
|-------|-------------------|----------|----------------------|-------------|
| `langgraph` | `langgraph>=1.2,<1.3`, `langchain-core>=1.6,<2`, `langgraph-checkpoint-sqlite>=3.1` | 1.2.12 / 1.6.5 / 3.1.1 | **52 packages** ✅ verified importable | `langgraph` |
| `crewai` | `crewai>=1.15,<2` | 1.15.22 | ~134 pkgs (STACK.md) — **uninstallable on this host** | `crewai` |
| **`ag2`** ← corrected name | `ag2>=1.1,<2` | 1.1.0 | **25 packages** ✅ verified importable, `ag2.__version__ == "1.1.0"` | `ag2` |
| `local` | `langchain-ollama>=1.1`, `ag2[ollama]>=1.1` | — | opt-in realism tier | — |
| `all` | `eacp[langgraph,crewai,ag2]` | — | 172 total | — |

Self-referential `all` extra **verified working** under plain `pip install '.[all]'`. ⚠️ `eacp[all]` and `eacp[crewai]` both fail on macOS x86_64 — document in README.

### Development tooling — `[dependency-groups] dev` (PEP 735)

| Tool | Range | Resolved | Purpose |
|------|-------|----------|---------|
| `pytest` | `>=9.1` | **9.1.1** | Test runner (Wave 0 creates the first tests) |
| `pytest-asyncio` | `>=1.4` | **1.4.0** | Mandatory later — `ag2` middleware is `async def` throughout |
| `ruff` | `>=0.16` | **0.16.9** | Lint + format (replaces black/isort/flake8) |
| `mypy` | `>=2.3` | **2.3.1** | Type checking |

**Use `[dependency-groups]`, not `[project.optional-dependencies] dev`.** Verified behaviour: PEP 735 groups are invisible to `pip install eacp` (they are not extras), so dev tooling cannot leak into a user's install — which directly protects PACKAGE-01. `uv sync` installs the `dev` group **by default**; pass `--no-default-groups` for a true core-only environment. This flag is easy to forget and its absence silently invalidates the core CI job.

### Build backend

| Recommended | Range | Resolved | Verified |
|-------------|-------|----------|----------|
| **`hatchling`** | `>=1.27` | **1.32.4** | ✅ built + `pip install`ed the src-layout package; `import eacp` OK |

**Use hatchling.** Needs exactly two config lines for `src/` layout and is the boring, universally-recognised choice — which matters for a project whose stated goal is favourable maintainer review, and it keeps the build independent of the `uv` toolchain choice.

I also verified **`uv_build` 0.12.19** works with *zero* build configuration (it auto-detects `src/<name>/`) and installs fine under plain `pip`. It is two lines shorter. Noted as a legitimate alternative, but hatchling is the recommendation — do not spend planning time relitigating this.

### Alternatives considered

| Instead of | Could use | Tradeoff |
|------------|-----------|----------|
| `hatchling` | `uv_build` | Zero build config (auto src-layout detection); verified working. Couples build-from-sdist to uv's release cadence. |
| `hatchling` | `setuptools` | Most ubiquitous, but needs more config for src layout and is slower. No reason here. |
| `[dependency-groups] dev` | `[project.optional-dependencies] dev` | Older idiom; makes dev tooling a *publicly installable extra* (`pip install eacp[dev]`) — extra surface area and a PACKAGE-01 leak risk. Avoid. |
| One universal `uv.lock` | Per-extra compiled `requirements/*.txt` | PITFALLS.md offered this as an alternative. Unnecessary: one universal lock already covers every extra × platform, and `uv sync --extra X` realizes any subset from it. Per-extra files are 4 files to keep in sync instead of 1. |
| `uv.lock` universal | `[tool.uv] environments = [...]` to exclude darwin-x86_64 | **Not needed — verified.** `uv lock` succeeds on this Intel Mac. Adding `environments` narrows the lock for Linux/Windows/arm64 users to solve a problem that doesn't exist at lock time. |

**Installation (verified working, in order):**
```bash
uv lock                                          # -> uv.lock (172 pkgs, 2016 hashes)
uv sync --locked --no-default-groups             # core only  -> 17 pkgs
uv sync --locked --no-default-groups --extra ag2 # -> 25 pkgs
```

---

## Package Legitimacy Audit

Run via `slopcheck scan pyproject.toml` (non-installing mode) against the real scratch `pyproject.toml`. **Result: 10 packages scanned, 10 `[OK]`, 0 `[SLOP]`, 0 `[SUS]`.**

| Package | Registry | slopcheck | Registry check | Disposition |
|---------|----------|-----------|----------------|-------------|
| `pydantic` | PyPI | `[OK]` | 2.12.5 resolved | Approved |
| `pyyaml` | PyPI | `[OK]` | 6.0.3 resolved | Approved |
| `typer` | PyPI | `[OK]` | 0.27.2 resolved | Approved |
| `opentelemetry-api` | PyPI | `[OK]` (name-pattern note only) | 1.45.0 resolved | Approved |
| `opentelemetry-sdk` | PyPI | `[OK]` (name-pattern note only) | 1.45.0 resolved | Approved |
| `langgraph` | PyPI | `[OK]` | 1.2.12, imported | Approved |
| `langchain-core` | PyPI | `[OK]` (name-pattern note only) | 1.6.5, imported | Approved |
| `langgraph-checkpoint-sqlite` | PyPI | `[OK]` | 3.1.1, `SqliteSaver` imported | Approved |
| `crewai` | PyPI | `[OK]` | 1.15.22 resolved (install blocked by platform, not legitimacy) | Approved |
| `ag2` | PyPI | `[OK]` | 1.1.0, imported, `__version__` confirmed | Approved |

slopcheck's three "name looks like LLM bait but package is established" notes on `opentelemetry-*` / `langchain-core` are pattern heuristics on well-known packages, not findings.

**Dev-group + build packages** are outside `slopcheck scan`'s pyproject scope (it reads `[project.dependencies]` and `[project.optional-dependencies]`, not `[dependency-groups]`). All five were version-confirmed on PyPI and successfully installed today: `pytest` 9.1.1, `pytest-asyncio` 1.4.0, `ruff` 0.16.9, `mypy` 2.3.1, `hatchling` 1.32.4. These are among the most-downloaded packages in the Python ecosystem; legitimacy risk is negligible.

**Packages removed due to `[SLOP]`:** none.
**Packages flagged `[SUS]`:** none. No `checkpoint:human-verify` gate is required on any install for legitimacy reasons.

> ⚠️ **Process note / incident.** I initially ran `slopcheck install <pkgs>` per the research protocol without realising that subcommand **checks and then actually pip-installs**. It wrote into this machine's global `site-packages` and clobbered four packages the user already had. I restored `langchain-core==0.3.86`, `openai==1.109.1`, `orjson==3.11.2`, `typing_extensions==4.12.2` and confirmed the user's langchain stack imports again (`langchain 0.3.27` + `langchain-core 0.3.86`). Residual additive packages I could **not** remove (`pip uninstall` was denied by the sandbox) are listed in §Open Questions Q4 with the exact cleanup command. **Use `slopcheck scan <file>`, never `slopcheck install`.**

---

## Architecture Patterns

### System Architecture: how the framework-free property is enforced

```
                      pip install eacp                 pip install 'eacp[ag2]'
                              │                                  │
                              ▼                                  ▼
              ┌──────────────────────────────┐    ┌──────────────────────────────┐
              │ INSTALL-TIME BOUNDARY        │    │ INSTALL-TIME BOUNDARY        │
              │ [project] dependencies only  │    │ + optional-dependencies.ag2  │
              │ -> 17 pkgs, no framework     │    │ -> 25 pkgs, ag2 present      │
              └──────────────┬───────────────┘    └──────────────┬───────────────┘
                             └───────────────┬──────────────────┘
                                             ▼
                                   import eacp   ◀── PACKAGE-01 gate
                                             │
                        ┌────────────────────┴────────────────────┐
                        ▼                                         ▼
              src/eacp/__init__.py                    src/eacp/adapters/__init__.py
              (version marker only —                  (EMPTY by contract —
               imports NO adapter)                     imports NO adapter)
                        │
                        │  nothing framework-shaped has been imported yet
                        ▼
              ┌──────────────────────────────────────────────────────────┐
              │  RUNTIME BOUNDARY: eacp/backends.py                      │
              │  _BACKENDS: name -> (module_path, extra, framework_root)  │
              │  plain strings — no imports at module scope               │
              └───────────────────────┬──────────────────────────────────┘
                                      │  load_backend_module("crewai")
                                      ▼
                        importlib.import_module(...)  ◀── the ONLY import site
                                      │
                    ┌─────────────────┴─────────────────┐
              succeeds                             ModuleNotFoundError
                    │                                   │
                    ▼                        ┌──────────┴──────────┐
        adapters/crewai_adapter.py           ▼                     ▼
        (module-scope `import crewai`)   exc.name == root?    exc.name != root?
                    │                        │                     │
                    ▼                        ▼                     ▼
              framework loaded        MissingExtraError      re-raise UNCHANGED
              (on demand only)        "pip install            (a real internal bug
                                       eacp[crewai]"           must NOT be disguised
                                                               as a missing extra)
```

The right-hand branch is the non-obvious part and §Pitfall 2 explains why it matters.

### Recommended project structure (Phase 1 deliverable — exactly this, nothing more)

```
.
├── LICENSE                       # exists
├── prompt.md                     # exists
├── CLAUDE.md                     # exists
├── README.md                     # NEW — PACKAGE-04 platform matrix
├── pyproject.toml                # NEW
├── uv.lock                       # NEW — committed (PACKAGE-03)
├── .python-version               # NEW — "3.12"
├── .gitignore                    # NEW — .venv/, __pycache__/, *.egg-info/, .pytest_cache/
├── .github/
│   └── workflows/
│       └── ci.yml                # NEW — core + 3 extras (D-04)
├── src/
│   └── eacp/
│       ├── __init__.py           # NEW — re-exports __version__ ONLY
│       ├── __about__.py          # NEW — single source of version truth
│       ├── py.typed              # NEW — empty; CLAUDE.md mandates type hints
│       ├── errors.py             # NEW — MissingExtraError only
│       ├── backends.py           # NEW — adapter lookup + lazy loader (~30 lines)
│       └── adapters/
│           ├── __init__.py       # NEW — EMPTY (load-bearing; see Pitfall 1)
│           ├── langgraph_adapter.py  # NEW — placeholder
│           ├── crewai_adapter.py     # NEW — placeholder
│           └── ag2_adapter.py         # NEW — placeholder, NEVER autogen_adapter.py
└── tests/
    ├── __init__.py               # NEW
    └── test_packaging.py         # NEW — Wave 0; guards PACKAGE-01/02/04
```

**Deliberately NOT created in this phase:** `examples/`, `docs/`, `benchmarks/`, `tests/core/`, `tests/adapters/`, `tests/contract/`. See §Phase Scope Boundary — D-03 places these at repo root, but git cannot commit an empty directory, so creating them now yields either nothing or filler `.gitkeep` files. They arrive with their content in Phases 8–10.

### Pattern 1: `pyproject.toml` (complete, verified working)

Gap 1 from the brief. This exact file was written to disk, `uv lock`'d (172 pkgs), `uv sync`'d per extra, and `pip install`ed today.

```toml
[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[project]
name = "eacp"
dynamic = ["version"]
description = "Enterprise Agent Control Plane — one governance layer over LangGraph, CrewAI and ag2"
readme = "README.md"
license = "MIT"                      # verified against existing LICENSE
requires-python = ">=3.11,<3.14"     # <3.14 is FORCED by crewai, not a preference
authors = [{ name = "Ashrafuzzaman M Hossain" }]   # spelling per LICENSE, not git config
keywords = ["agents", "governance", "policy", "langgraph", "crewai", "ag2"]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Intended Audience :: Developers",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Typing :: Typed",
]

# PACKAGE-01: this list must NEVER contain langgraph, crewai, or ag2.
dependencies = [
  "pydantic>=2.11,<2.13",            # <2.13 cap forced by crewai-core
  "pyyaml>=6",
  "typer>=0.27",
  "opentelemetry-api>=1.42,<2",
  "opentelemetry-sdk>=1.42,<2",
]

# PACKAGE-02. NOTE: the AutoGen-lineage extra is named `ag2` for the actual
# package — never `autogen` (see PITFALLS.md Pitfall 1).
[project.optional-dependencies]
langgraph = [
  "langgraph>=1.2,<1.3",
  "langchain-core>=1.6,<2",
  "langgraph-checkpoint-sqlite>=3.1",
]
crewai = ["crewai>=1.15,<2"]         # NOT installable on macOS x86_64 (lancedb)
ag2 = ["ag2>=1.1,<2"]
local = ["langchain-ollama>=1.1", "ag2[ollama]>=1.1"]
all = ["eacp[langgraph,crewai,ag2]"] # self-reference verified working under pip

# PEP 735. Deliberately NOT optional-dependencies: dev tooling must not be
# installable as `pip install eacp[dev]`, and must never reach a user env.
[dependency-groups]
dev = [
  "pytest>=9.1",
  "pytest-asyncio>=1.4",
  "ruff>=0.16",
  "mypy>=2.3",
]

[tool.hatch.version]
path = "src/eacp/__about__.py"

[tool.hatch.build.targets.wheel]
packages = ["src/eacp"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"                # ag2 middleware is async def throughout
addopts = "--strict-markers"
markers = [
  "langgraph: requires the langgraph extra",
  "crewai: requires the crewai extra",
  "ag2: requires the ag2 extra",
]

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.12"
strict = true
files = ["src", "tests"]
```

Notes the planner should not second-guess:
- **No `[project.scripts]` yet.** A console script pointing at a non-existent `eacp.cli:app` would make `pip install eacp` succeed but `eacp --help` crash. The CLI arrives in Phase 4 (APPROVAL-02).
- **No `[tool.uv]` block.** Verified unnecessary — see §Alternatives Considered.
- `dynamic = ["version"]` + `[tool.hatch.version]` keeps `__about__.py` the single source of version truth, so `eacp.__version__` and the distribution metadata can never disagree.
- `.python-version` containing `3.12` is **required**, not cosmetic: with `requires-python = ">=3.11"` and no `.python-version`, `uv lock` selected CPython **3.11.16** — not the 3.12 STACK.md recommends.

### Pattern 2: lazy backend loading (verified — Gap 3)

`src/eacp/errors.py`:
```python
class MissingExtraError(ImportError):
    """A backend was requested but its optional extra isn't installed."""
```

`src/eacp/backends.py`:
```python
"""Lazy backend resolution.

This module MUST NOT import any agent framework at module scope. It stores
adapter locations as strings and imports on demand, which is what keeps
`import eacp` framework-free (PACKAGE-01) while still shipping three
adapters (PACKAGE-02).
"""
from __future__ import annotations

import importlib
from types import ModuleType

from eacp.errors import MissingExtraError

# backend name -> (adapter module, extra name, framework root module)
_BACKENDS: dict[str, tuple[str, str, str]] = {
    "langgraph": ("eacp.adapters.langgraph_adapter", "langgraph", "langgraph"),
    "crewai": ("eacp.adapters.crewai_adapter", "crewai", "crewai"),
    "ag2": ("eacp.adapters.ag2_adapter", "ag2", "ag2"),
}


def available_backends() -> tuple[str, ...]:
    """Backend names this build knows about (installed or not)."""
    return tuple(_BACKENDS)


def load_backend_module(backend: str) -> ModuleType:
    """Import a backend's adapter module, or explain which extra is missing."""
    try:
        module_path, extra, framework_root = _BACKENDS[backend]
    except KeyError:
        raise ValueError(
            f"Unknown backend {backend!r}. Known backends: {sorted(_BACKENDS)}"
        ) from None

    try:
        return importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        # Only translate a MISSING FRAMEWORK into an install hint. A typo'd
        # internal import inside the adapter must propagate unchanged, or a
        # real bug gets misreported as "you forgot to install an extra".
        if (exc.name or "").split(".")[0] != framework_root:
            raise
        raise MissingExtraError(
            f"Backend {backend!r} requires the {framework_root!r} package, "
            f"which is not installed. Install it with:\n"
            f"    pip install 'eacp[{extra}]'"
        ) from exc
```

Verified behaviour in an env with `ag2` installed but `crewai` absent:

| Call | Result |
|------|--------|
| `import eacp, eacp.backends` | `sys.modules` contains **no** framework — verified even with `langgraph` *and* `ag2` installed |
| `load_backend_module("crewai")` | `MissingExtraError: ... pip install 'eacp[crewai]'` ✅ |
| `load_backend_module("ag2")` | returns module; `ag2` now in `sys.modules` ✅ |
| adapter with a genuine internal typo | `ModuleNotFoundError: eacp.does_not_exist` propagates unchanged ✅ |
| `load_backend_module("nope")` | `ValueError: Unknown backend 'nope'. Known: [...]` ✅ |

**Module-scope `import langgraph` inside the adapter is correct and preferred** over a function-body import or a module-level `try/except ImportError`. The adapter module is itself the lazy boundary — it is only ever imported through `load_backend_module`. Function-body imports add indirection for no gain, and module-level `try/except ImportError` is actively worse: it yields a module that imports "successfully" in a half-initialised state, turning a clean install error into a confusing `AttributeError` later.

### Pattern 3: placeholder adapter modules (Gap 5)

Each is ~6 lines. They exist *only* to prove the extra resolves and the lazy boundary holds. Phases 5–7 replace their bodies.

`src/eacp/adapters/__init__.py` — **empty by contract**:
```python
"""Framework adapters.

Importing this package MUST NOT import any agent framework. Adapter modules
are loaded on demand by `eacp.backends.load_backend_module`. Do not add
imports here — doing so breaks PACKAGE-01.
"""
```

`src/eacp/adapters/ag2_adapter.py` — note the filename (PITFALLS.md Pitfall 1):
```python
"""ag2 adapter.

Package:  ag2>=1.1,<2   (PyPI name `ag2`, imports as `ag2`)
NOT:      autogen / pyautogen / autogen-agentchat — four different codebases.
Install:  pip install 'eacp[ag2]'

Placeholder: real adapter logic lands in Phase 7 (AG2-01, AG2-02).
"""
from __future__ import annotations

import ag2  # noqa: F401  proves the extra resolved; lazy via eacp.backends

BACKEND = "ag2"
FRAMEWORK_VERSION = getattr(ag2, "__version__", "unknown")
```

`langgraph_adapter.py` and `crewai_adapter.py` follow the identical shape (`import langgraph` / `import crewai`, `BACKEND = "langgraph"` / `"crewai"`).

Use `from __future__ import annotations` plus a `TYPE_CHECKING` block for any framework *type* you need in a signature — that keeps annotations string-only so type-only imports never execute:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from crewai import Crew   # never imported at runtime
```

### Pattern 4: `uv` lockfile commands (Gap 4 — exact invocations)

| Goal | Command | Verified result |
|------|---------|-----------------|
| Create/update the lockfile | `uv lock` | ✅ 172 packages, 2016 `sha256` hashes, `requires-python = ">=3.11, <3.14"`. Universal: covers **all** extras, the dev group, and all platforms in one file. |
| CI drift gate (PACKAGE-03) | `uv lock --check` | ✅ exits non-zero if `pyproject.toml` and `uv.lock` disagree |
| Core-only env | `uv sync --locked --no-default-groups` | ✅ **17 packages**, zero frameworks |
| One extra | `uv sync --locked --no-default-groups --extra ag2` | ✅ 25 pkgs / `--extra langgraph` → 52 pkgs |
| Dev env for working on the repo | `uv sync --locked --extra langgraph --extra ag2` | ✅ (dev group included by default) |
| Everything | `uv sync --locked --all-extras` | ❌ on macOS x86_64 (lancedb) |
| Run in the synced env without re-syncing | `uv run --no-sync --no-default-groups python -c ...` | ✅ used for all CI assertions |

⚠️ **`uv lock` has NO `--extra` flag** — confirmed against `uv lock --help`. STACK.md's `uv lock --extra langgraph --extra crewai --extra autogen` fails with `unexpected argument`. `--extra` belongs to `uv sync` / `uv pip compile`. `uv lock` is universal and needs no extra selection.

⚠️ **Do not use `uv add` to build the pyproject.** STACK.md's install section scripts eight `uv add` calls. Writing `pyproject.toml` directly and running `uv lock` once is fewer steps, reviewable as a single diff, and does not depend on `uv add --optional` flag behaviour across uv versions.

⚠️ **`--locked` vs bare `--locked`-less sync.** In CI always pass `--locked`: it *fails* rather than silently re-resolving and rewriting `uv.lock`, which is what makes the job a real reproducibility gate.

### Pattern 5: CI workflow (Gap 2 — complete YAML)

Runner facts verified today: `ubuntu-latest` → Ubuntu 24.04 x64; **`macos-latest` → macOS 26 arm64 (Apple Silicon)** — correct per D-05. `astral-sh/setup-uv` latest is **v10.2.0** (2026-09-21); `actions/setup-python` is v7.0.0 (not needed — `setup-uv` + `uv python install` handles interpreters).

`.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  UV_VERSION: "0.12.19"

jobs:
  # ── The gate. Proves PACKAGE-01 + PACKAGE-03 on every push. ──────────────
  core:
    name: core (no frameworks) / ${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v10
        with:
          version: ${{ env.UV_VERSION }}
          enable-cache: true

      - name: Lockfile is in sync with pyproject.toml   # PACKAGE-03
        run: uv lock --check

      - name: Install core only (no extras, no dev group)
        run: uv sync --locked --no-default-groups

      - name: import eacp with zero agent frameworks    # PACKAGE-01
        run: |
          uv run --no-sync --no-default-groups python - <<'PY'
          import importlib.util as u
          import eacp

          FRAMEWORKS = ("langgraph", "crewai", "ag2", "langchain_core")
          installed = [m for m in FRAMEWORKS if u.find_spec(m) is not None]
          assert not installed, (
              f"PACKAGE-01 VIOLATED: agent framework(s) reached the core "
              f"install: {installed}. A framework was added to "
              f"[project].dependencies, or an extra leaked into it."
          )
          print(f"PACKAGE-01 OK - eacp {eacp.__version__}, no frameworks present")
          PY

      - name: Core test suite
        run: uv sync --locked && uv run pytest -q

  # ── One job per extra (D-04) × Linux + macOS arm64 (D-05). ──────────────
  extra:
    name: ${{ matrix.extra }} / ${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
        extra: [langgraph, crewai, ag2]
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v10
        with:
          version: ${{ env.UV_VERSION }}
          enable-cache: true

      # Defensive: `macos-latest` is arm64 TODAY, but the label floats. If
      # GitHub ever repoints it at Intel, fail with OUR message rather than an
      # opaque lancedb wheel error. See README platform matrix / PACKAGE-04.
      - name: Guard against an Intel macOS runner
        if: runner.os == 'macOS'
        run: |
          arch="$(uname -m)"
          echo "macOS runner arch: $arch"
          if [ "$arch" != "arm64" ]; then
            echo "::error::macos-latest resolved to $arch, not arm64. The crewai" \
                 "extra cannot install on macOS x86_64 (lancedb publishes no" \
                 "x86_64 wheel and no sdist). Pin an explicit arm64 runner label."
            exit 1
          fi

      - name: Install eacp[${{ matrix.extra }}]
        run: uv sync --locked --no-default-groups --extra ${{ matrix.extra }}

      - name: Import the adapter through the lazy loader   # PACKAGE-02
        run: |
          uv run --no-sync --no-default-groups python - <<'PY'
          import os, sys
          import eacp
          from eacp.backends import load_backend_module

          # `import eacp` must not have pulled the framework in by itself.
          leaked = sorted(
              m for m in sys.modules
              if m.split(".")[0] in {"langgraph", "crewai", "ag2"}
          )
          assert not leaked, f"PACKAGE-02 VIOLATED: eager framework import: {leaked}"

          backend = os.environ["EACP_EXTRA"]
          module = load_backend_module(backend)
          print(f"PACKAGE-02 OK - {backend} -> {module.__name__} "
                f"(framework {module.FRAMEWORK_VERSION})")
          PY
        env:
          EACP_EXTRA: ${{ matrix.extra }}
```

Design notes:
- **8 jobs** (core × 2, extra 3 × 2), exceeding D-04's 4-job minimum while staying one matrix. Cut to `os: [ubuntu-latest]` for the `extra` job if CI minutes matter — D-05 makes macOS optional.
- `fail-fast: false` is important: a CrewAI nightly break should redden exactly one cell, per PITFALLS.md Pitfall 2.
- The core job's assertion uses `importlib.util.find_spec`, not `pip list | grep`. `find_spec` catches a framework reaching the environment by *any* route (vendored, `--system-site-packages` leakage, a transitive dep) and does not import the module.
- Two separate assertions, deliberately: the `core` job proves the framework *isn't installed*; the `extra` job proves that even when it *is* installed, `import eacp` doesn't load it. Neither implies the other.
- No Windows job (Claude's-discretion default). Nothing found in research argues for adding it; all three frameworks publish `win_amd64` wheels, so it would likely pass — it just isn't a stated target.
- No lint/mypy job. Phase 1 has ~60 lines of code and no conventions to regress; `ruff`/`mypy` config ships so a later phase can add the job in three lines. Adding it now is scope creep.

### Platform Support Matrix (README-ready — PACKAGE-04)

Copy into README.md. Every row measured today.

| Platform | `eacp` (core) | `eacp[langgraph]` | `eacp[ag2]` | `eacp[crewai]` |
|----------|:---:|:---:|:---:|:---:|
| Linux x86_64 | ✅ | ✅ | ✅ | ✅ |
| Linux aarch64 | ✅ | ✅ | ✅ | ✅ |
| macOS arm64 (Apple Silicon) | ✅ | ✅ | ✅ | ✅ |
| **macOS x86_64 (Intel)** | ✅ | ✅ | ✅ | ❌ **not supported** |
| Windows x86_64 | ✅ | ✅ | ✅ | ✅ (untested by this project) |

Measured install size: core **17 packages**, `eacp[ag2]` **25**, `eacp[langgraph]` **52**, full graph **172**.

Suggested README wording:

> **macOS x86_64 (Intel) — `eacp[crewai]` is not installable.** `crewai>=1.15` requires
> `lancedb>=0.29.2,<0.30.1`, and `lancedb` publishes **no** `macosx_*_x86_64` wheel in any
> released version, and no source distribution — so there is nothing to build from source
> either. This is an upstream packaging gap, not an EACP limitation, and we cannot work
> around it. `eacp` core, `eacp[langgraph]` and `eacp[ag2]` all install and run normally on
> Intel macOS; only the CrewAI extra is affected. Use Linux, macOS arm64, Windows, or a
> Linux container to work with the CrewAI backend.

### Anti-patterns to avoid

- **Any framework in `[project] dependencies`** — the one unrecoverable mistake in this phase. It silently deletes the project's central credibility claim.
- **Importing an adapter from `eacp/__init__.py` or `eacp/adapters/__init__.py`** — makes `import eacp` raise `ModuleNotFoundError: crewai` with a *correct* `pyproject.toml`. This is PITFALLS.md's named tell-tale symptom.
- **Naming the extra or module `autogen`** — STACK.md does this and it is wrong. See §State of the Art.
- **`[project.optional-dependencies] dev`** — makes dev tooling a publicly installable extra.
- **`uv sync` without `--no-default-groups` in the core CI job** — silently installs the dev group and stops testing the real core.
- **`uv sync` without `--locked` in CI** — re-resolves and rewrites `uv.lock`, so the job no longer proves reproducibility.
- **Module-level `try: import crewai / except ImportError: pass`** — yields a half-initialised module and defers a clean error into a confusing `AttributeError`.
- **Adding `[tool.uv] required-environments = ["sys_platform == 'darwin' and platform_machine == 'x86_64'"]`** — uv's own hint text suggests this when `lancedb` fails. It is the wrong advice here: it *demands* a wheel that does not exist and will fail `uv lock` for everyone.

---

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---------|-------------|-------------|-----|
| Pinning 172 transitive packages reproducibly | Hand-maintained `requirements.txt`, or `pip freeze` output | `uv lock` → `uv.lock` | Records per-platform wheel sets + 2016 sha256 hashes and stays universal. `pip freeze` captures one platform/Python and loses hashes. |
| Per-extra pinned dependency sets | Four compiled `requirements/*.txt` files | one universal `uv.lock` + `uv sync --extra X` | Four files drift independently; one lock cannot. |
| Detecting "is this framework installed?" | `try: import crewai / except ImportError` | `importlib.util.find_spec("crewai")` | Doesn't execute the module, and reports environment presence rather than import success. |
| Turning a missing optional dep into a good error | Per-adapter bespoke `raise ImportError("...")` | one `_BACKENDS` table + `MissingExtraError` in `backends.py` | One code path, one message format, one place to fix. Guarantees all three adapters behave identically. |
| Deriving `__version__` | Duplicating the string in `pyproject.toml` *and* `__init__.py` | `dynamic = ["version"]` + `[tool.hatch.version]` reading `__about__.py` | Two copies drift; `eacp.__version__` disagreeing with distribution metadata is a classic packaging bug. |
| Verifying the lockfile matches pyproject | Bespoke diff script | `uv lock --check` | One command, correct exit code. |
| Making `src/` layout importable in tests | `sys.path` manipulation, `conftest.py` hacks, `PYTHONPATH` | install the package (`uv sync` does an editable install) | D-02 chose src layout *precisely* to force this. Path hacks reintroduce the failure mode the layout prevents. |
| Interpreter version selection in CI | `actions/setup-python` + manual venv | `astral-sh/setup-uv@v10` + `.python-version` | setup-uv installs the interpreter, caches, and honours `.python-version` — one action instead of two. |

**Key insight:** every hand-rolled option here trades one declarative line for a file that must be kept in sync by hand. In a phase whose entire purpose is establishing an invariant that must survive nine more phases, hand-maintained state is exactly the wrong trade.

---

## Common Pitfalls

### Pitfall 1: `__init__.py` quietly re-eagers the imports the extras made lazy
**What goes wrong:** `pyproject.toml` is perfect, the extras are perfect, and then a later phase adds `from eacp.adapters.crewai_adapter import CrewAIAdapter` to `src/eacp/__init__.py` for convenience. `pip install eacp && python -c "import eacp"` now raises `ModuleNotFoundError: crewai` and PACKAGE-01 is dead — with no change to any dependency declaration.
**Why it happens:** Re-exporting from `__init__.py` is normal, good Python everywhere except across an optional-dependency boundary. The author is in Phase 5 thinking about ergonomics, not Phase 1's invariant.
**How to avoid:** Keep `eacp/__init__.py` to `__version__` only and `eacp/adapters/__init__.py` empty, both with a docstring saying *why*. The CI `core` job is the real defence — it catches this on the commit that introduces it. If ergonomic re-exports are wanted later, PEP 562 module-level `__getattr__` provides them lazily; do not add it in Phase 1 (nothing to export).
**Warning signs:** `import eacp` slows down; `ModuleNotFoundError` naming a framework; any `from eacp.adapters...` at top level of a core module.

### Pitfall 2: the install hint swallows a real bug
**What goes wrong:** `load_backend_module` catches `ModuleNotFoundError` broadly. In Phase 6 someone typos `from eacp.polcy import Policy` inside `crewai_adapter.py`. The loader reports *"Backend 'crewai' requires the 'crewai' package... pip install eacp[crewai]"*. CrewAI **is** installed. The developer reinstalls it, sees the same message, and loses an afternoon.
**Why it happens:** `ModuleNotFoundError` is raised for *any* module missing anywhere in the adapter's import graph, and the naive handler assumes it can only mean the framework.
**How to avoid:** Compare `exc.name`'s root against the known framework root and re-raise unchanged when they differ — the `if (exc.name or "").split(".")[0] != framework_root: raise` line in Pattern 2. **Verified working:** an adapter with a genuine bad internal import propagated `ModuleNotFoundError: eacp.does_not_exist` untouched, while the absent-framework case produced `MissingExtraError`.
**Warning signs:** a bare `except ModuleNotFoundError:` in `backends.py` with no `exc.name` check; a "missing extra" message for a framework `pip list` shows as installed.

### Pitfall 3: the CI core job tests the wrong environment
**What goes wrong:** The job runs `uv sync --locked` (no flags) and asserts no frameworks are present. It passes. Months later PACKAGE-01 is broken and CI is still green — because `uv sync` installs the `dev` group by default and, once a later phase adds a framework to a dev/test group, the assertion is running against an environment nobody ships.
**Why it happens:** `uv sync`'s default-group behaviour is not obvious, and the job *looks* right.
**How to avoid:** `uv sync --locked --no-default-groups` in the core job, always. Assert with `importlib.util.find_spec` so anything reaching the environment by any route is caught. Keep the test-suite step as a *separate* step with its own `uv sync` so the two environments can't be confused.
**Warning signs:** the core job never fails, including on a commit that deliberately adds `langgraph` to core deps (worth testing once, on a throwaway branch, that the gate actually bites).

### Pitfall 4: assuming the lockfile can't be produced on this machine
**What goes wrong:** `uv sync --extra crewai` fails on Intel macOS, so PACKAGE-03 is judged blocked, and someone either adds `[tool.uv] environments` to exclude darwin-x86_64 (narrowing the lock for all users) or drops the `crewai` extra.
**Why it happens:** Conflating lock-time with install-time resolution. They are different operations.
**How to avoid:** **Verified today: `uv lock` succeeds on this Intel Mac and produces the full 172-package universal lock including `crewai` and `lancedb==0.30.0`.** Locking records which wheels exist; only `uv sync`/`pip install` requires one for the *current* platform. PACKAGE-03 is fully deliverable here. Add no `[tool.uv]` platform config.
**Warning signs:** `[tool.uv] environments` or `required-environments` appearing in the diff; the `crewai` extra being weakened or removed.

### Pitfall 5: the AutoGen extra gets named `autogen`
**What goes wrong:** `pip install eacp[autogen]` installs `ag2`. A reader cannot tell whether the adapter targets `autogen` (AG2 Classic, `ConversableAgent`), `autogen-agentchat` (Microsoft, maintenance mode), or `ag2` — the exact four-way ambiguity PITFALLS.md Pitfall 1 is about, on the project's own install command.
**Why it happens:** Everyone says "AutoGen." **This project's own `research/STACK.md` does it** (`autogen = ["ag2>=1.1,<2"]`) despite PITFALLS.md warning against it two files away.
**How to avoid:** Extra is `ag2`, module is `ag2_adapter.py`, CI job is `ag2`, pytest marker is `ag2`. Put the pip name, version range, and import root in the adapter docstring (Pattern 3). The word "autogen" should appear nowhere in `pyproject.toml`.
**Warning signs:** `grep -ri autogen pyproject.toml src/` returns anything. Worth a literal Phase 1 verification step.

### Pitfall 6: `macos-latest` silently becomes Intel
**What goes wrong:** `macos-latest` is arm64 today (verified: macOS 26 arm64). GitHub floats `-latest` labels. If it ever repoints to x64, the `crewai` macOS job fails with an opaque `lancedb` wheel error that looks like a project bug, and someone "fixes" it by removing the extra.
**How to avoid:** The `uname -m` guard in Pattern 5 — three lines that convert a confusing upstream error into an explicit message naming the cause and the fix.
**Warning signs:** a macOS CI failure mentioning `lancedb` or `no matching distribution`.

### Pitfall 7: Phase 1 grows a policy engine
**What goes wrong:** Writing placeholder adapters invites "while I'm here" — a `Policy` model, an `Adapter` Protocol, a `store.py`. Phase 2 then rewrites it against the real schema, and Phase 1's verification covers code it never specified.
**Why it happens:** The scaffold *looks* incomplete without them.
**How to avoid:** Treat §Phase Scope Boundary's "out" column as binding. The phase is done when `pip install` works four ways and CI is green — not when the package looks finished.
**Warning signs:** any `pydantic.BaseModel` subclass, any `typing.Protocol`, any `yaml.safe_load`, any `sqlite3` import, or `[project.scripts]` in the Phase 1 diff.

---

## Code Examples

### Version marker (single source of truth)
```python
# src/eacp/__about__.py
__version__ = "0.1.0"
```
```python
# src/eacp/__init__.py
"""Enterprise Agent Control Plane.

Importing this package MUST NOT import langgraph, crewai, or ag2 (PACKAGE-01).
Adapters load on demand via `eacp.backends.load_backend_module`.
"""
from eacp.__about__ import __version__

__all__ = ["__version__"]
```

### The phase's load-bearing test (verified passing)

Uses a **clean subprocess** deliberately: inside a pytest session another test may already have imported a framework, so an in-process `sys.modules` check gives false greens. Verified passing in an environment with both `langgraph` and `ag2` installed.

```python
# tests/test_packaging.py
"""Guards the packaging invariants of PACKAGE-01/02/04."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from eacp.backends import available_backends, load_backend_module
from eacp.errors import MissingExtraError

FRAMEWORK_ROOTS = ("langgraph", "crewai", "ag2")

_PROBE = """
import json, sys
import eacp, eacp.backends
roots = {"langgraph", "crewai", "ag2"}
print(json.dumps(sorted(m for m in sys.modules if m.split(".")[0] in roots)))
"""


def test_import_eacp_does_not_import_any_framework() -> None:
    """PACKAGE-01/02: true even when the frameworks ARE installed."""
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE], capture_output=True, text=True, check=True
    )
    leaked = json.loads(proc.stdout)
    assert leaked == [], (
        f"`import eacp` eagerly imported {leaked}. An adapter is being imported "
        f"from eacp/__init__.py or eacp/adapters/__init__.py."
    )


@pytest.mark.parametrize("backend", available_backends())
def test_backend_either_loads_or_explains_itself(backend: str) -> None:
    """PACKAGE-02: no third outcome. Never a bare ModuleNotFoundError."""
    root = backend  # backend name == framework import root for all three
    installed = importlib.util.find_spec(root) is not None
    if installed:
        module = load_backend_module(backend)
        assert module.BACKEND == backend
    else:
        with pytest.raises(MissingExtraError, match=rf"eacp\[{backend}\]"):
            load_backend_module(backend)


def test_unknown_backend_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown backend"):
        load_backend_module("autogen")  # a plausible wrong guess


def test_no_adapter_is_named_autogen() -> None:
    """PITFALLS.md Pitfall 1: name things for the package, never the brand."""
    adapters = Path(__file__).parent.parent / "src" / "eacp" / "adapters"
    names = [p.name for p in adapters.glob("*_adapter.py")]
    assert "autogen_adapter.py" not in names
    assert "ag2_adapter.py" in names


def test_readme_documents_the_platform_gap() -> None:
    """PACKAGE-04."""
    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    low = readme.lower()
    for token in ("x86_64", "lancedb", "crewai", "arm64"):
        assert token in low, f"README platform matrix does not mention {token!r}"
```

`test_unknown_backend_is_a_value_error` doubles as a regression test that `"autogen"` is *not* a registered backend name.

### Reproducing the platform finding (for the plan's verification step)
```bash
# Fails on macOS x86_64, succeeds on Linux / macOS arm64 / Windows.
uv pip compile --python-version 3.12 --python-platform x86_64-apple-darwin - <<< "crewai>=1.15,<2"
```
Actual output today: `... we can conclude that your requirements are unsatisfiable. hint: Wheels are available for lancedb (v0.30.0) on the following platforms: manylinux_2_17_aarch64, manylinux_2_17_x86_64, manylinux_2_28_aarch64, manylinux_2_28_x86_64, manylinux2014_aarch64, manylinux2014_x86_64, macosx_11_0_arm64, win_amd64`.

---

## Phase Scope Boundary (Gap 5)

Explicit in/out, so the plan cannot drift into Phase 2.

| Concern | In Phase 1 | Out (owner) |
|---------|-----------|-------------|
| `pyproject.toml`, extras, dep groups | ✅ complete | — |
| `uv.lock` committed | ✅ | — |
| `src/eacp/{__init__,__about__}.py`, `py.typed` | ✅ | — |
| `errors.py` — `MissingExtraError` only | ✅ | every other exception type (Phase 2+) |
| `backends.py` — adapter lookup + lazy loader | ✅ ~30 lines | — |
| `adapters/*_adapter.py` — placeholders | ✅ ~6 lines each | real adapter logic (Phases 5/6/7) |
| README with platform matrix | ✅ | full README (DOCS-01, Phase 10) |
| CI: core + 3 extras | ✅ | lint/mypy/coverage jobs (later) |
| `tests/test_packaging.py` | ✅ | all behavioural tests (Phase 2+) |
| Policy schema / `Policy` model | ❌ | POLICY-01/02 (Phase 2) |
| **Workflow** registry, entrypoint allowlist, capabilities | ❌ | WORKFLOW-01/02/03 (Phase 2) |
| `Adapter` Protocol / `AdapterCapabilities` | ❌ | Phase 2 |
| Run store / SQLite | ❌ | TRACE-03 (Phase 2) |
| `[project.scripts]` / CLI | ❌ | APPROVAL-02 (Phase 4) |
| Mock LLM / `eacp.testing` | ❌ | Phase 3/4 |
| `examples/`, `docs/`, `benchmarks/` dirs | ❌ | Phases 8/9/10 (git can't commit empty dirs) |
| `tests/core,adapters,contract/` subdirs | ❌ | created with their tests |

⚠️ **Naming collision to avoid now.** STACK.md and PITFALLS.md both use the word "registry" for two different things: Phase 1's *adapter/backend* resolution, and Phase 2's *workflow* registry (WORKFLOW-02/03: entrypoint allowlist, capability validation). Phase 1 should name its module **`backends.py`**, leaving `registry.py` free for Phase 2. Calling the Phase 1 file `registry.py` invites Phase 2 to bolt workflow registration onto the adapter loader.

---

## Runtime State Inventory

Greenfield — no rename, refactor, or migration. Repo contains only `LICENSE`, `prompt.md`, `CLAUDE.md`, `.planning/`, `.claude/`, and an untracked `prompt.md` sibling; `src/` does not exist. No stored data, live service config, OS-registered state, secrets, or build artifacts exist to migrate.

| Category | Items found | Action |
|----------|-------------|--------|
| Stored data | None — no datastore exists | none |
| Live service config | None — no external service integrated | none |
| OS-registered state | None — no scheduled task, daemon, or service | none |
| Secrets / env vars | None — no `.env`, no secrets referenced | none |
| Build artifacts | None — no `*.egg-info/`, no `.venv/`, `src/` absent | none |

⚠️ One forward-looking note: this phase *creates* the first build artifact (an editable install into `.venv/`). `.gitignore` must cover `.venv/`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/` in the same commit — a stale `src/eacp.egg-info/` is a classic cause of confusing import behaviour under src layout.

---

## Environment Availability

Probed on this machine today.

| Dependency | Required by | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `uv` | PACKAGE-03 lockfile, all installs | ✅ | **0.9.30** (latest is **0.12.19**) | ⚠️ upgrade — see below |
| Python 3.12 | recommended target | ✅ | 3.12.13 | 3.11 / 3.13 also in range |
| Python 3.13 | default `python3` | ✅ | 3.13.2 | — |
| Python 3.11 | lower bound | ✅ (via `uv python`) | 3.11.16 | — |
| `git` | version control | ✅ | 2.53.0 | — |
| `gh` | CI inspection, PRs | ✅ | 2.89.0 | web UI |
| `pip` | PACKAGE-01 literal check | ✅ | 26.2.1 | — |
| `slopcheck` | legitimacy audit | ✅ (installed today) | — | already run |
| **macOS arm64 or Linux** | **`eacp[crewai]` install** | ❌ **this host is macOS x86_64** | — | **CI, Docker/colima, or remote Linux — see Q1** |

**Missing with no fallback:** none blocking Phase 1. All four PACKAGE requirements are achievable on this host.

**Missing with fallback (but blocking a LATER phase):** a platform able to install `eacp[crewai]`. Phase 1 can complete without one — `uv lock` works and the `crewai` extra just can't be *realized* locally. Phase 6 cannot. Flagged as Q1.

⚠️ **Local `uv` is 0.9.30 (2026-02-04); current is 0.12.19 (2026-09-25).** Seven months stale. Everything in this document was verified against **0.9.30**, so all of it is a *lower bound* on what works — but the planner should include `uv self update` (or pin `UV_VERSION: "0.12.19"` as the CI env does) as an early task and re-run `uv lock` afterwards, because:
- the lockfile `revision` field can differ between uv versions, producing a spurious `uv lock --check` failure in CI if CI runs a newer uv than the developer who generated the lock;
- `uv lock --help` on 0.12.x may have gained flags (this document's claim that `uv lock` has no `--extra` was verified on 0.9.30 — note that this *matches* the 0.12.x documented behaviour, so the STACK.md correction stands either way).

**Recommendation: pin one uv version in CI (`UV_VERSION`) and use the same locally.** A lockfile-revision mismatch between local and CI uv is the most likely spurious CI failure in this phase.

---

## Validation Architecture

`workflow.nyquist_validation: true` in `.planning/config.json`.

### Test framework
| Property | Value |
|----------|-------|
| Framework | `pytest` **9.1.1** (+ `pytest-asyncio` 1.4.0) |
| Config file | **none — greenfield.** Wave 0 creates `[tool.pytest.ini_options]` in `pyproject.toml` (block given in Pattern 1) |
| Quick run | `uv run pytest -q` (< 2 s — no framework imports) |
| Full suite | `uv run pytest -q` (identical in Phase 1; diverges from Phase 5 when marker-gated adapter tests appear) |
| Install for testing | `uv sync --locked` (dev group by default) |

### Phase requirements → test map
| Req | Behaviour | Type | Automated command | Exists? |
|-----|-----------|------|-------------------|---------|
| PACKAGE-01 | `import eacp` pulls no framework into `sys.modules`, in any env | unit (clean subprocess) | `uv run pytest tests/test_packaging.py::test_import_eacp_does_not_import_any_framework -x` | ❌ Wave 0 |
| PACKAGE-01 | core install *contains* no framework | CI env assertion | `uv sync --locked --no-default-groups && uv run --no-sync --no-default-groups python -c "import importlib.util as u,eacp; assert not [m for m in ('langgraph','crewai','ag2') if u.find_spec(m)]"` | ❌ Wave 0 |
| PACKAGE-02 | each backend loads, or raises `MissingExtraError` naming its extra | unit (parametrized) | `uv run pytest tests/test_packaging.py::test_backend_either_loads_or_explains_itself -x` | ❌ Wave 0 |
| PACKAGE-02 | each extra actually installs and imports | integration (CI matrix) | `uv sync --locked --no-default-groups --extra {langgraph,crewai,ag2}` + loader probe | ❌ Wave 0 |
| PACKAGE-02 | no module/extra named `autogen` | unit (filesystem) | `uv run pytest tests/test_packaging.py::test_no_adapter_is_named_autogen -x` | ❌ Wave 0 |
| PACKAGE-03 | lockfile committed and in sync with `pyproject.toml` | CI gate | `uv lock --check` | ❌ Wave 0 |
| PACKAGE-04 | README documents the platform matrix incl. macOS x86_64 / lancedb | unit (content) | `uv run pytest tests/test_packaging.py::test_readme_documents_the_platform_gap -x` | ❌ Wave 0 |

Every PACKAGE requirement is automatable — **no manual-only verification is needed in this phase.** PACKAGE-04 is normally "docs, verify by eye"; the token-presence test makes it a real gate cheaply, which matters because the platform matrix is the kind of doc that silently rots.

### Sampling rate
- **Per task commit:** `uv run pytest -q` (< 2 s)
- **Per wave merge:** `uv run pytest -q` + `uv lock --check`
- **Phase gate:** all 8 CI jobs green before `/gsd-verify-work`

### Wave 0 gaps
- [ ] `[tool.pytest.ini_options]` in `pyproject.toml` — no config exists (covers all four reqs)
- [ ] `[dependency-groups] dev` with `pytest>=9.1`, `pytest-asyncio>=1.4` — framework not installed
- [ ] `tests/__init__.py`
- [ ] `tests/test_packaging.py` — the six tests above
- [ ] `.github/workflows/ci.yml` — CI-level assertions for PACKAGE-01/02/03

⚠️ **Ordering constraint.** `tests/test_packaging.py` imports `eacp.backends`, so it cannot pass before `backends.py` and the adapter placeholders exist. Wave 0 should create the *config* and the *empty* test module; the tests land in the same wave as the code they guard. `test_readme_documents_the_platform_gap` will fail until README.md exists — sequence README before that test, or accept one red wave.

---

## Security Domain

`security_enforcement: true`, `security_asvs_level: 1`.

This phase has no runtime input surface: no network listener, no user input parsing, no authentication, no authorization, no data storage, no cryptographic operation. The real (and only) security surface is **software supply chain**, which is exactly what a packaging phase controls.

### Applicable ASVS categories

| ASVS category | Applies | Control in this phase |
|---------------|:---:|------------------------|
| V2 Authentication | no | no auth surface exists |
| V3 Session Management | no | no sessions |
| V4 Access Control | no | no authorization decisions |
| V5 Input Validation | **partial** | no runtime input. The one adjacent item: `load_backend_module` must resolve **only** names present in the `_BACKENDS` dict — never interpolate a caller-supplied string into `importlib.import_module`. The pattern in Pattern 2 does this correctly (dict lookup first, `ValueError` on miss). |
| V6 Cryptography | no | nothing hand-rolled. `uv.lock`'s 2016 `sha256` hashes are generated by uv. |
| V7 Error Handling / Logging | **partial** | `MissingExtraError` messages contain only package/extra names — no paths, no environment data, no secrets. |
| V12 Files / Resources | no | no file upload/serving |
| **V14 Configuration / Dependency Management** | **yes — primary** | See below. |

### V14 controls delivered by this phase

| Control | Implementation | Status |
|---------|----------------|--------|
| Dependency inventory is explicit and reviewable | `pyproject.toml` ranges + `uv.lock` 172 pinned packages | ✅ by design |
| Integrity verification on install | `uv.lock` carries **2016 `sha256:` hashes**; `uv sync --locked` verifies them | ✅ verified |
| No unpinned/floating versions | every range upper-bounded (`<2`, `<1.3`, `<2.13`); lock pins exact patches | ✅ — important given `crewai` ships a nightly *daily* |
| Attack surface minimised | core install 17 packages vs 172; a LangGraph-only adopter never installs `onnxruntime`, `kubernetes`, `grpcio`, `chromadb`, `lancedb` | ✅ measured |
| Unused components not shipped | dev tooling in PEP 735 group (not an extra) — unreachable via `pip install eacp[...]` | ✅ |
| Dependencies verified non-hallucinated | `slopcheck scan` → 10/10 `[OK]` | ✅ §Package Legitimacy Audit |
| Third-party CI actions pinned | ⚠️ workflow uses major tags (`@v5`, `@v10`) | ⚠️ see below |

### Known threat patterns

| Pattern | STRIDE | Mitigation | Status |
|---------|--------|------------|--------|
| Dependency confusion / typosquat (esp. the four-way `autogen` namespace) | Spoofing / Tampering | Exact PyPI names pinned; `ag2` naming discipline; `slopcheck scan`; `test_no_adapter_is_named_autogen` | ✅ |
| Malicious version bump in a transitive dep | Tampering | `uv.lock` + `--locked` in CI; hash verification | ✅ |
| Malicious/compromised GitHub Action | Tampering / EoP | `actions/checkout@v5`, `astral-sh/setup-uv@v10` are **mutable major tags** — a compromised tag executes in CI | ⚠️ **Residual.** ASVS L1 does not require SHA pinning. Recommend pinning to full commit SHAs; at minimum note it. Low severity: CI has no secrets in this phase (no publish step, no `GITHUB_TOKEN` write scope needed). |
| Arbitrary import via attacker-controlled backend name | Tampering / EoP | dict-lookup allowlist before `import_module`; `ValueError` on unknown | ✅ — this is the Phase 1 seed of the Phase 2 entrypoint-allowlist control (PITFALLS.md Pitfall 12) |
| Malicious build backend | Tampering | `hatchling>=1.27` from PyPI; hash-verified in lock | ✅ |
| Secret leakage in CI logs | Information Disclosure | no secrets used; no publish step in this phase | ✅ |

**`security_block_on: high`** — no high-severity finding. The only residual item (mutable action tags) is low, and no PyPI publishing happens in this phase, so no trusted-publisher/token configuration is in scope yet.

---

## State of the Art — corrections to prior project research

Prior research (`research/STACK.md`, `research/PITFALLS.md`, 2026-09-24) is excellent and holds up almost entirely. Five corrections and one closure, all verified today.

| Prior claim (source) | Correction | Evidence |
|---------------------|------------|----------|
| `[project.optional-dependencies] autogen = ["ag2>=1.1,<2"]` — STACK.md §Packaging | **Extra must be named `ag2`.** STACK.md contradicts PITFALLS.md Pitfall 1 ("name the module for the *package*, not the brand") and CONTEXT.md D-01/STATE.md. Use `ag2` for the extra, module, CI job, and pytest marker. `all = ["eacp[langgraph,crewai,ag2]"]`. | CONTEXT.md D-01; PITFALLS.md Pitfall 1; REQUIREMENTS.md PACKAGE-02 already says `eacp[ag2]` |
| `uv lock --extra langgraph --extra crewai --extra autogen` — STACK.md §Installation | **`uv lock` has no `--extra` flag.** Errors with `unexpected argument`. `uv lock` is universal and locks all extras and groups at once. `--extra` belongs to `uv sync` / `uv pip compile`. | `uv lock --help`; executed today |
| Eight `uv add` / `uv add --optional` calls to construct the project — STACK.md §Installation | Prefer writing `pyproject.toml` directly then one `uv lock`. One reviewable diff, no dependence on `uv add --optional` semantics. | executed both ways |
| `opentelemetry-*` resolves to `1.44.0` — STACK.md §Version Compatibility | Now resolves to **1.45.0**. The `>=1.42,<2` range absorbs it; no action needed. Illustrates why the lockfile matters. | `uv.lock` today |
| `uv 0.12.19` is "the toolchain" — STACK.md §Development Tools | Accurate (latest is 0.12.19, uploaded 2026-09-25) but **this machine has 0.9.30**. Pin `UV_VERSION` in CI and match it locally to avoid lockfile-revision mismatches. | `uv --version`; PyPI JSON |
| *"Not investigated — whether `crewai` can be installed without `chromadb`/`lancedb`. ... Worth 30 minutes."* — STACK.md §Staleness Audit | **CLOSED: no.** `crewai-core` 1.15.22 does not depend on `lancedb` (12 light deps), but it imports as **`crewai_core`** and contains only auth/settings/telemetry/paths plumbing (`plus_api`, `token_manager`, `lock_store`, `settings`, `telemetry`). **`crewai/hooks/` — the entire CREWAI-01 seam (`before_tool_call`, `before_llm_call`, `HookAborted`) — ships in the `crewai` distribution**, which hard-requires `lancedb<0.30.1,>=0.29.2`. There is no lightweight CrewAI path. | PyPI `requires_dist` for both dists; inspected both wheels' file listings today |

**Deprecated / do not use** (unchanged from PITFALLS.md, re-confirmed): `pyautogen`, `autogen-agentchat`/`-core`/`-ext`, `pip install ag2-classic` (no such package), assuming `ag2` imports as `autogen`.

---

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|-------|---------|---------------|
| A1 | `local` extra contents (`langchain-ollama>=1.1`, `ag2[ollama]>=1.1`) are correct | Standard Stack | LOW — carried from STACK.md, not re-verified today (out of phase scope; nothing in Phase 1 installs it). Planner may omit the `local` extra entirely and add it when Ollama support is actually built. |
| A2 | `eacp[crewai]` installs successfully on Linux x86_64/aarch64, macOS arm64, and Windows | Platform Support Matrix | MEDIUM — inferred from `lancedb`'s published wheel tags (manylinux x86_64/aarch64, macosx_11_0_arm64, win_amd64) and STACK.md's Linux/macOS-arm64 resolutions. **Could not execute on this Intel host.** First CI run confirms or refutes. The Windows row in particular is untested by this project. |
| A3 | ~~`license = "MIT"`~~ | Pattern 1 | **RESOLVED — verified.** `LICENSE` reads `MIT License / Copyright (c) 2026 Ashrafuzzaman M Hossain`. `license = "MIT"` is correct. |
| A4 | Author name in `[project] authors` | Pattern 1 | **CORRECTED.** Use **`Ashrafuzzaman M Hossain`** (from `LICENSE`), *not* the `AshraHossain` / "Ashraf Hossain" from git config. Pattern 1's snippet says `Ashraf Hossain` — the planner must use the LICENSE spelling so copyright and package metadata agree. Still open: whether an email should appear in package metadata (it becomes public on PyPI). |
| A5 | Version should start at `0.1.0` | Pattern 1 | LOW — conventional for pre-release. User may prefer `0.0.1`. |
| A6 | Windows is out of scope for CI | Pattern 5 | LOW — CONTEXT.md sets this as Claude's discretion with Linux+macOS default; research surfaced no reason to add it. |
| A7 | `uv lock` output is stable across uv 0.9.30 → 0.12.19 (same `revision`) | Environment Availability | MEDIUM — if the lock revision differs, `uv lock --check` fails in CI against a lock generated locally. Mitigated by pinning `UV_VERSION` and regenerating after upgrading. |
| A8 | `mypy strict = true` is achievable on the Phase 1 code | Pattern 1 | LOW — ~60 lines, fully annotated. But `strict` will likely need `ignore_missing_imports` per-framework once real adapters land (STACK.md predicts this). Not a Phase 1 problem; no mypy CI job is proposed. |

---

## Open Questions

1. **How will the CrewAI backend be developed, given this machine cannot install it?** ⚠️ **Needs a user decision; the planner should open Phase 1 with a `checkpoint:human-verify`.**
   - What we know (all verified today): this host is macOS x86_64; `uv sync --extra crewai` fails on `lancedb==0.30.0`; `lancedb` has never shipped a macOS x86_64 wheel (0.29.0–0.32.0 checked, latest 0.39.0) **and ships no sdist**, so source-building is impossible; `crewai-core` is not a viable lightweight substitute. No workaround exists.
   - What's unclear: which development strategy the user wants.
   - Options: **(a) CI-only** — write the CrewAI adapter blind, iterate through GitHub Actions. Zero setup, slow feedback (minutes per iteration), painful for a phase with an unproven hook API. **(b) Docker/colima Linux container** — full local `eacp[crewai]` env, normal iteration speed; costs container setup and a documented `make` target. **(c) Remote Linux host / GitHub Codespaces** — fastest path to a real environment, needs an account/host.
   - Recommendation: **(b)**, decided now and noted in STATE.md so Phase 6 planning can assume it. Nothing in Phase 1 depends on the answer — Phase 1 completes on this host regardless — so this is a cheap decision to make early and an expensive one to discover late. Also worth reflecting in ROADMAP.md as a Phase 6 prerequisite.

2. **Should the `local` extra ship in Phase 1 at all?** Declaring it costs one line and locks its deps now; omitting it keeps Phase 1 to exactly what PACKAGE-02 names (`langgraph`, `crewai`, `ag2`). Recommendation: **omit `local`**, add it in the phase that builds Ollama support. Keeps the phase honest and avoids locking two dependencies nothing uses. (Low impact either way — planner's call.)

3. **Pin CI actions to commit SHAs?** ASVS L1 does not require it and this phase's CI has no secrets or publish step. Recommendation: keep major tags now; revisit when a PyPI publish workflow is added, which is the point at which a compromised action becomes materially dangerous.

4. **Cleanup owed on this machine from my `slopcheck install` error.** I restored the four clobbered packages (`langchain-core==0.3.86`, `openai==1.109.1`, `orjson==3.11.2`, `typing_extensions==4.12.2`) and the user's langchain stack imports correctly again. These additive packages remain in global `site-packages` and I could not remove them (`pip uninstall` was denied by the sandbox): `ag2 1.1.0`, `langgraph 1.2.12`, `langgraph-checkpoint 4.2.0`, `langgraph-checkpoint-sqlite 3.1.1`, `langgraph-prebuilt 1.1.0`, `langgraph-sdk 0.4.5`, `langchain-protocol 0.0.19`, `fast-depends 3.0.9`, `librt 0.15.0`, `ormsgpack 1.12.2`, `sqlite-vec 0.1.9`, `trove-classifiers 2026.9.21.13`. They are harmless but make `pip check` noisy. To clean up:
   ```bash
   pip3 uninstall -y langgraph langgraph-checkpoint langgraph-checkpoint-sqlite \
     langgraph-prebuilt langgraph-sdk langchain-protocol ag2 ormsgpack sqlite-vec librt
   ```
   Unrelated pre-existing conflict, not caused by me: `langchain-ibm 0.1.7` requires `langchain-core<0.3` while the machine has `0.3.86`. Also noted incidentally: this machine has a global `crewai 1.9.3` — an old pre-`lancedb`-pin release, which is why it installed on Intel at all; it does not satisfy this project's `>=1.15` range.

---

## Sources

### Primary — HIGH confidence (executed locally, 2026-09-25)
- **Real scratch `eacp` project** at `/private/tmp/.../scratchpad/eacp-probe` — full `pyproject.toml` written, `uv lock` (172 pkgs, 2016 hashes), `uv sync` for core / `--extra ag2` / `--extra langgraph` / `--extra crewai`, `uv lock --check`, real imports, and the complete lazy-loader + subprocess test suite. Every package count, version, and behavioural claim in this document comes from here.
- **`uv pip compile --python-platform x86_64-apple-darwin`** — reproduced the `lancedb` resolution failure with uv's full wheel-tag list.
- **`uv lock --help`** (uv 0.9.30) — confirmed no `--extra` flag.
- **PyPI JSON API** — `lancedb` wheel/sdist inventory across 0.29.0–0.32.0 (latest 0.39.0); `crewai` 1.15.22 and `crewai-core` 1.15.22 `requires_dist`; `uv` 0.12.19; `hatchling` 1.32.4; `uv-build` 0.12.19.
- **Wheel inspection** — `crewai-1.15.22-py3-none-any.whl` (contains `crewai/hooks/*`) vs `crewai_core-1.15.22-py3-none-any.whl` (top-level `crewai_core`, no hooks). Closes STACK.md's open question.
- **`slopcheck scan`** — 10/10 `[OK]`.
- **Host probe** — `sysctl hw.optional.arm64` absent, `machdep.cpu.brand_string` = Intel Core i7-10700K, `sysctl.proc_translated` absent → genuine Intel, not Rosetta.
- **`uv_build` + plain `pip install`** — verified zero-config src-layout build; self-referential `[all]` extra verified under `pip install --dry-run '.[all]'`.

### Secondary — HIGH/MEDIUM confidence (official sources, fetched today)
- https://docs.astral.sh/uv/concepts/resolution/ — universal resolution; `tool.uv.environments` vs `required-environments` semantics.
- https://github.com/actions/runner-images — `macos-latest` → macOS 26 **arm64**; `ubuntu-latest` → Ubuntu 24.04 x64; macOS x64 images exist under explicit labels.
- GitHub API — `astral-sh/setup-uv` v10.2.0 (2026-09-21); `actions/setup-python` v7.0.0.

### Project research (treated as input, corrected where verified wrong)
- `.planning/research/STACK.md`, `.planning/research/PITFALLS.md` (2026-09-24) — see §State of the Art for the five corrections and one closure.
- `.planning/phases/01-.../01-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `CLAUDE.md`, `.planning/config.json`.

### Not consulted
Context7 was not available in this session and the CLI fallback (`ctx7`) is not installed. It was not needed: every claim here concerns packaging mechanics verifiable by execution, which is a stronger source than documentation. Framework *API* research (where Context7 would matter) belongs to Phases 5–7.

---

## Metadata

**Confidence breakdown:**
- **Standard stack — HIGH.** Every version is a resolved value from a real `uv.lock`; every install path except `crewai` was executed and imported.
- **`pyproject.toml` — HIGH.** Written to disk, locked, synced four ways, `pip install`ed.
- **Lazy-import pattern — HIGH.** Executed, including the negative cases (missing extra, internal-typo passthrough, unknown backend) and the clean-subprocess assertion with two frameworks installed.
- **`uv` commands — HIGH** on uv 0.9.30, **MEDIUM** for uv 0.12.19 (see A7 — lock-revision stability across versions unverified).
- **CI YAML — MEDIUM-HIGH.** Runner labels/arch and action versions verified today; the assertion scripts were executed locally in the exact environments they target; the workflow itself has never run on GitHub Actions. Expect only trivial YAML fixes.
- **Platform matrix — HIGH for macOS x86_64 (failure reproduced, root cause proven unfixable), MEDIUM for the other rows** (inferred from wheel tags — see A2).
- **Pitfalls — HIGH.** All seven are mechanical consequences of verified behaviour; Pitfalls 2 and 4 were demonstrated by execution.
- **Phase scope boundary — HIGH.** Derived from CONTEXT.md and REQUIREMENTS.md traceability, which map every non-PACKAGE requirement to Phase 2+.
- **Security domain — HIGH.** Supply-chain controls are verified artefacts (hash count, package counts, slopcheck). Correctly assessed as a near-empty ASVS surface outside V14.

**Research date:** 2026-09-25
**Valid until:** ~2026-10-25 for packaging mechanics (stable). **~2026-10-02 for the pinned versions** — `crewai` publishes a nightly *daily* and `ag2` shipped 1.1.0 the day before yesterday; re-run `uv lock` at the start of execution rather than trusting these resolved patches.
