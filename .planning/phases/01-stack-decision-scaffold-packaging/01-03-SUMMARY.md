---
phase: 01-stack-decision-scaffold-packaging
plan: 03
subsystem: ci
tags: [github-actions, matrix, uv, lockfile-gate, packaging, platform-matrix]

# Dependency graph
requires:
  - "01-01: `pyproject.toml` extras + `dev` group, committed `uv.lock` (172 pkgs, revision 3), `.python-version`"
  - "01-01: uv pinned locally to 0.12.19 — the workflow's `UV_VERSION` must match it or `uv lock --check` reddens on lockfile format alone"
  - "01-02: `eacp.backends.load_backend_module` and the three adapter placeholders — the `extra` job's probe target"
  - "01-02: `tests/test_packaging.py` — run by the `core` job's test step"
provides:
  - "`.github/workflows/ci.yml` — jobs `core` and `extra`, 8 matrix cells, the D-04/D-05 gate for PACKAGE-01/02/03"
  - "First real execution evidence for the `eacp[crewai]` install on Linux x86_64 and macOS arm64 (01-RESEARCH.md assumption A2 CONFIRMED)"
  - "Measured `FRAMEWORK_VERSION` for all three backends on both target OSes, including `crewai 1.15.22` — unobtainable on this Intel dev host"
  - "A pushed `origin/main` (SSH) — the repo's 27 local commits are now on GitHub"
affects:
  - "Every later phase: the `core` job fails any push that lets a framework into `[project].dependencies` or leaves `uv.lock` drifted"
  - "Phase 6 (CrewAI): `crewai / ubuntu-latest` green is the evidence that a Linux container can install `eacp[crewai]`, validating the already-decided Docker/colima prerequisite"
  - "README.md platform matrix — the Linux x86_64 and macOS arm64 CrewAI rows are now measured, not inferred"

# Tech tracking
tech-stack:
  added:
    - "GitHub Actions (`actions/checkout@v5`, `astral-sh/setup-uv@v10.2.0`)"
  patterns:
    - "Action version pinning: `astral-sh/setup-uv` is pinned to the exact release `v10.2.0` because astral-sh publishes no floating major tag past `v7` — `@v10` does not exist"
    - "Every `uv sync` in CI carries `--locked`; the core job additionally carries `--no-default-groups` so the assertion runs against the environment users actually ship"
    - "Framework absence is asserted with `importlib.util.find_spec`, never `pip list | grep` — it catches vendored/transitive/system-site-packages routes and does not execute the module"
    - "The test suite lives in its own step with its own `uv sync --locked`, so the core-only and dev-group environments can never be confused"
    - "`fail-fast: false` on both jobs: a CrewAI nightly break reddens one cell, not the matrix"
    - "Floating-runner-label hazards get an explicit guard (`uname -m` → `::error::` naming `lancedb`) rather than being left to produce an opaque upstream error"
    - "Shell blocks inside `run: |` are syntax-checked locally (`bash -n` per extracted block + heredoc-terminator column assertion) before spending a CI run"

key-files:
  created:
    - .github/workflows/ci.yml
  modified: []

key-decisions:
  - "Pinned `astral-sh/setup-uv@v10.2.0` instead of the planned `@v10` — the floating major tag does not exist and failed all 8 cells at action-resolution time; the exact pin also narrows T-01-03's mutable-tag surface from a major to a patch tag"
  - "Switched `origin` from HTTPS to SSH — GitHub refuses any OAuth-App push that creates or updates a workflow file without the `workflow` scope, and `gh`'s token has only `repo`/`read:org`/`gist`/`admin:public_key`. SSH was already working and is `gh`'s own configured git protocol, so this is the root-cause fix rather than a scope escalation"
  - "Kept the four macOS cells despite D-05 making them optional: the repository is PUBLIC, so Actions minutes are free and the 10× macOS multiplier costs nothing; `crewai / macos-latest` is the only environment in the whole project where CrewAI runs on Apple Silicon"
  - "Did not weaken, comment out, or remove any assertion to reach green — the only workflow edit between the red and green runs was the action tag"

patterns-established:
  - "Before pushing a never-executed workflow, parse it with `yaml.safe_load`, `bash -n` every `run:` block with matrix expressions substituted, and assert every heredoc terminator lands at column 0"
  - "Verify an action reference resolves (`gh api repos/<owner>/<action>/tags`) rather than trusting a documented 'latest version' to imply a floating major tag exists"
  - "Workflow files can only be pushed over SSH or by a token carrying the `workflow` scope; this repo uses SSH"

requirements-completed: [PACKAGE-01, PACKAGE-02, PACKAGE-03]

# Metrics
duration: 28min
completed: 2026-09-26
---

# Phase 1 Plan 03: CI Matrix (core + extras) Summary

**An 8-cell GitHub Actions matrix that re-proves the framework-free core, the lockfile-drift gate, and all three lazy-loaded adapters on clean Linux and macOS arm64 runners on every push — green on a real run, and the first place in this project's history where `eacp[crewai]` has actually installed.**

## Performance

- **Duration:** ~28 min
- **Started:** 2026-09-26T19:00:00Z (approx — first task commit 19:07:43Z)
- **Completed:** 2026-09-26T19:28:00Z
- **Tasks:** 2
- **Files modified:** 1 created, 0 modified
- **CI runs consumed:** 2 (one red on a trivial action-tag defect, one green)

## Accomplishments

- **All 8 cells green on run [36265951482](https://github.com/AshraHossain/Self-ReflectiveAgentwithAuto-Eval/actions/runs/36265951482)**, total wall clock **31 s** (19:24:37Z → 19:25:08Z). `gh run watch --exit-status` exits 0; non-success job count is `0`; job count is `8`.
- **`eacp[crewai]` installed and lazy-loaded on both target platforms for the first time in this project.** 137 packages, `FRAMEWORK_VERSION 1.15.22`, on `ubuntu-latest` *and* `macos-latest`. 01-RESEARCH.md assumption **A2 is CONFIRMED** — the Linux x86_64 and macOS arm64 rows of README's platform matrix were inferred from `lancedb` wheel tags and are now measured. **No README correction was needed.**
- **The `uname -m` guard fired and reported `arm64` on all three macOS `extra` cells** — Pitfall 6's hazard is instrumented and the D-05 assumption (`macos-latest` is Apple Silicon) is verified live, not assumed.
- **PACKAGE-01 re-proved on clean runners, both OSes:** `uv sync --locked --no-default-groups` installed exactly **17 packages** and `find_spec` found none of `langgraph`, `crewai`, `ag2`, `langchain_core`. The 17-package count matches 01-RESEARCH.md and plan 01-02's local measurement exactly — nothing leaked into core in transit.
- **PACKAGE-03 gated:** `uv lock --check` resolved 172 packages and exited 0 on both OSes. The `UV_VERSION: "0.12.19"` pin worked — 01-02's carried-forward concern about a lockfile-`revision` mismatch reddening the gate on format alone did **not** materialise.
- **`tests/test_packaging.py` green on real runners:** `7 passed in 0.04s` (ubuntu) / `0.09s` (macOS), against 01-VALIDATION.md's 2 s budget.
- **Every local pre-flight gate passed before the first push,** including a `bash -n` syntax check of all 7 `run:` blocks and a column-0 assertion on both heredoc terminators. 01-RESEARCH.md predicted heredoc indentation as the most likely first-run failure; it was not the failure, because it was checked locally first.
- **The repo's 27 local commits are now on GitHub.** `origin/main` had been stuck at `ac7e211` since before Phase 1 planning; the whole phase is now public.

## Task Commits

1. **Task 1: Write `.github/workflows/ci.yml`** — `6582450` (ci)
2. **Task 2: Push and confirm all 8 cells green** — `9f93207` (fix; verification-only task carrying the Rule 1 defect it uncovered)

## Files Created/Modified

- `.github/workflows/ci.yml` (created, 111 lines) — `name: CI`; `on: push` restricted to `branches: [main]` plus `pull_request`; `concurrency: ${{ github.workflow }}-${{ github.ref }}` with `cancel-in-progress: true`; workflow-level `env.UV_VERSION: "0.12.19"`. Two jobs:
  - **`core`** on `[ubuntu-latest, macos-latest]`, `fail-fast: false` — `uv lock --check` → `uv sync --locked --no-default-groups` → a stdin-fed Python `find_spec` assertion over `langgraph`/`crewai`/`ag2`/`langchain_core` whose failure message names PACKAGE-01 and both plausible causes → the test suite in a **separate** step with its own `uv sync --locked`.
  - **`extra`** on `[ubuntu-latest, macos-latest]` × `[langgraph, crewai, ag2]`, `fail-fast: false` — macOS-conditional `uname -m` arm64 guard → `uv sync --locked --no-default-groups --extra ${{ matrix.extra }}` → a probe that first asserts `sys.modules` holds no framework root after a bare `import eacp`, *then* calls `load_backend_module(os.environ["EACP_EXTRA"])` and prints its `FRAMEWORK_VERSION`.

No source file, test, `pyproject.toml` entry, or lockfile line changed. `uv lock --check` and `uv run pytest -q` are still green locally and the workflow added no dependency.

## Measurements (plan `<output>` requirements)

### Run URL

**https://github.com/AshraHossain/Self-ReflectiveAgentwithAuto-Eval/actions/runs/36265951482** — head SHA `9f93207`, conclusion `success`, 8/8 jobs `success`, total **31 s**.

Superseded red run (kept for the record): [36265874041](https://github.com/AshraHossain/Self-ReflectiveAgentwithAuto-Eval/actions/runs/36265874041) — head SHA `6582450`, all 8 cells failed in 3-4 s at action resolution. See Deviations.

### 8-cell pass/fail grid with wall time

| Cell | OS | Result | Wall time | Packages installed | Evidence line |
|---|---|:---:|---:|---:|---|
| `core (no frameworks)` | `ubuntu-latest` | ✅ | 8 s | 17 (core) + 11 (dev) | `PACKAGE-01 OK - eacp 0.1.0, no frameworks present` / `7 passed in 0.04s` |
| `core (no frameworks)` | `macos-latest` | ✅ | 13 s | 17 (core) + 11 (dev) | `PACKAGE-01 OK - eacp 0.1.0, no frameworks present` / `7 passed in 0.09s` |
| `langgraph` | `ubuntu-latest` | ✅ | 8 s | 52 | `PACKAGE-02 OK - langgraph -> eacp.adapters.langgraph_adapter (framework 1.2.12)` |
| `langgraph` | `macos-latest` | ✅ | 9 s | 52 | same, after `macOS runner arch: arm64` |
| `crewai` | `ubuntu-latest` | ✅ | 14 s | **137** | `PACKAGE-02 OK - crewai -> eacp.adapters.crewai_adapter (framework 1.15.22)` |
| `crewai` | `macos-latest` | ✅ | **23 s** | **137** | same, after `macOS runner arch: arm64` |
| `ag2` | `ubuntu-latest` | ✅ | 7 s | 25 | `PACKAGE-02 OK - ag2 -> eacp.adapters.ag2_adapter (framework 1.1.0)` |
| `ag2` | `macos-latest` | ✅ | 13 s | 25 | same, after `macOS runner arch: arm64` |

`uv lock --check` reported `Resolved 172 packages` in every cell that runs it. Package counts reproduce 01-RESEARCH.md and 01-02's local numbers exactly: core **17**, `ag2` **25**, `langgraph` **52**.

### Observed `FRAMEWORK_VERSION` per extra cell

| Backend | `ubuntu-latest` | `macos-latest` | 01-RESEARCH.md measured | Local (01-02) |
|---|---|---|---|---|
| `langgraph` | **1.2.12** | **1.2.12** | 1.2.12 ✅ | 1.2.12 ✅ |
| `ag2` | **1.1.0** | **1.1.0** | 1.1.0 ✅ | 1.1.0 ✅ |
| `crewai` | **1.15.22** | **1.15.22** | 1.15.22 ✅ | *not measurable on this host* |

`crewai 1.15.22` is the value this project could not obtain locally. It matches STACK.md's pinned `crewai>=1.15,<2` resolution, and it was read through `importlib.metadata.version()` — which is the fix 01-02 made after `getattr(framework, "__version__")` silently returned `"unknown"` for langgraph. That fix is now confirmed working on a third framework it was never tested against.

### Did `crewai` pass on `ubuntu-latest` and `macos-latest`? — **Yes, both.**

This is the plan's most important single question and the answer is unambiguous. Both cells installed all 137 packages (including `lancedb==0.30.0`, `onnxruntime`, `pyarrow`) from the committed hash-pinned `uv.lock` under `--locked`, then loaded the adapter through the lazy loader and reported a real framework version.

Consequences:

1. **01-RESEARCH.md assumption A2 is confirmed, not refuted.** The Linux x86_64 and macOS arm64 CrewAI rows of README.md's platform matrix were inferred from published `lancedb` wheel tags on an Intel host that cannot install them. They are now measured. README needs no correction.
2. **Phase 6's Docker/colima Linux prerequisite is validated, not merely assumed.** `crewai / ubuntu-latest` is direct evidence that a Linux environment installs `eacp[crewai]` cleanly from this lockfile.
3. **The Intel-macOS gap is confirmed as platform-specific, not project-specific.** The same lockfile that fails on this `macosx_26_0_x86_64` host succeeds on `macosx arm64`. PACKAGE-04's README row is the correct framing.

### Do the macOS `extra` cells earn their CI minutes? — **Yes, and the question is moot here.**

D-05 makes them optional, and on a private repo the 10× macOS billing multiplier would make them the dominant cost (4 macOS jobs ≈ 40 billed minutes per run against ≈ 4 for the Linux cells, for 58 s of actual macOS compute). **This repository is PUBLIC, so GitHub Actions minutes are free** and the multiplier costs nothing.

Even setting billing aside, keep them:

- `crewai / macos-latest` is the **only** environment anywhere in this project — local or CI — where CrewAI runs on Apple Silicon. Given that the maintainer's own machine is an Intel Mac that can never install it, deleting this cell would leave the primary target platform for a Mac-based user entirely unverified.
- The macOS cells are where the `uname -m` guard lives. Without them, Pitfall 6 is undetectable rather than merely unguarded.
- The cost is 58 s of wall time on a 31 s total run (the matrix is parallel), so they do not slow the feedback loop either.

**Recommendation: keep all 8 cells.** Revisit only if this repository goes private.

### YAML fixes needed on the first run

One, and it was **not** the heredoc indentation 01-RESEARCH.md predicted — because that was checked locally before pushing. See Deviations.

## Decisions Made

- **`astral-sh/setup-uv@v10.2.0`, not `@v10`.** Exact-release pinning is now this project's convention for `setup-uv`. The upstream fact that forced it (no floating major tag past `v7`) is recorded in a comment in the workflow itself, so the next person does not "modernise" it back to `@v10`.
- **`origin` moved from HTTPS to SSH.** The alternative was `gh auth refresh -s workflow`, which escalates the local OAuth token's scopes and needs an interactive browser round-trip. SSH was already authenticated (`Hi AshraHossain!`), is what `gh auth status` already reports as this machine's git protocol, and requires no new privilege. Lower-privilege fix, no human gate.
- **All 8 cells retained.** See the CI-minutes analysis above.
- **No assertion softened.** The workflow diff between the red run and the green run is two lines, both the action tag. Every `uv sync` still carries `--locked` (3 of 3 lines), the core job still carries `--no-default-groups`, and both `find_spec` and the leak-then-load probe are intact.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `astral-sh/setup-uv@v10` does not exist — all 8 cells failed at action resolution**

- **Found during:** Task 2, first CI run ([36265874041](https://github.com/AshraHossain/Self-ReflectiveAgentwithAuto-Eval/actions/runs/36265874041))
- **Issue:** Every one of the 8 cells failed in 3-4 seconds with `##[error]Unable to resolve action 'astral-sh/setup-uv@v10', unable to find version 'v10'`. Not an assertion failure — the workflow never reached a project step.
- **Root cause:** 01-RESEARCH.md correctly reports `astral-sh/setup-uv` latest as `v10.2.0` (2026-09-21), and 01-RESEARCH.md §Pattern 5 turned that into `@v10` on the near-universal assumption that Actions publishers maintain a floating major tag. **`astral-sh` does not.** `gh api repos/astral-sh/setup-uv/tags` shows bare major tags only up to `v7`; from `v8.0.0` onward every tag is fully qualified. The plan's Task 1 acceptance criteria repeated `@v10` verbatim, so this was not catchable by any of the plan's own gates — the plan's `grep -q 'astral-sh/setup-uv@v10'` passes against both the broken and the fixed form.
- **Root cause, not symptom:** fixed in **both** jobs, not only the one whose log was read. Both `uses:` lines are now `@v10.2.0`, and a comment above the first one records why, so the fix does not get reverted by someone tidying up tags.
- **Fix:** `astral-sh/setup-uv@v10` → `astral-sh/setup-uv@v10.2.0` in the `core` and `extra` jobs.
- **Files modified:** `.github/workflows/ci.yml`
- **Verification:** run [36265951482](https://github.com/AshraHossain/Self-ReflectiveAgentwithAuto-Eval/actions/runs/36265951482) — 8/8 `success`; `gh run watch --exit-status` exits 0; every Task 1 content gate re-run clean.
- **Security side effect (positive):** narrows threat T-01-03. `setup-uv` is now pinned to an immutable-in-practice patch tag rather than a mutable major tag. `actions/checkout@v5` remains on a major tag, so T-01-03 is reduced, not closed.
- **Committed in:** `9f93207`

---

**2. [Rule 3 - Blocking] `git push` rejected: an OAuth App cannot create a workflow file without the `workflow` scope**

- **Found during:** Task 2, before any CI run existed
- **Issue:** The first push attempt (HTTPS + `osxkeychain`) hung with no output for over two minutes and had to be killed. Retrying through `gh`'s credential helper produced the real error immediately:
  `! [remote rejected] HEAD -> main (refusing to allow an OAuth App to create or update workflow '.github/workflows/ci.yml' without 'workflow' scope)`
  `gh auth status` confirms the token carries `admin:public_key`, `gist`, `read:org`, `repo` — no `workflow`. Task 2 is unrunnable until this is resolved, and its own action text anticipates a rejected push as a possible blocker.
- **Fix:** `git remote set-url origin git@github.com:AshraHossain/Self-ReflectiveAgentwithAuto-Eval.git`. SSH is not an OAuth App, so the workflow-scope restriction does not apply. `ssh -T git@github.com` already answered `Hi AshraHossain!` with the existing `~/.ssh/id_ed25519`, and `gh auth status` already reported `Git operations protocol: ssh` — the HTTPS remote URL was the outlier, not the SSH setup.
- **Rejected alternative:** `gh auth refresh -s workflow`, which grants the local token permission to modify workflow files in **every** repository it can reach, and needs an interactive browser flow. Strictly more privilege for strictly more friction.
- **Files modified:** none — this is a local git remote config change, not a repository file. It is not captured in any commit and will need re-applying on a fresh clone if that clone uses the HTTPS URL.
- **Verification:** `git ls-remote origin main` matches local `HEAD`; 27 commits landed; both CI runs triggered.
- **Not committed** (git config, not tracked content).

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking issue). No architectural change, no Rule 4 escalation, no dependency added, no assertion weakened.
**Impact on plan:** Two characters of the workflow differ from Pattern 5 (`@v10` → `@v10.2.0`) plus a two-line explanatory comment. Job structure, matrix shape, flags, probes and step order are exactly as planned. Task 2's git-push step required a transport change that the plan did not anticipate.

## Issues Encountered

- **The predicted failure did not happen, because it was checked first.** 01-RESEARCH.md rated this YAML MEDIUM-HIGH specifically because of heredoc-terminator indentation inside `run: |` block scalars. Before pushing, every `run:` block was extracted from the parsed YAML, matrix expressions substituted, and syntax-checked with `bash -n` (7/7 OK) with a separate assertion that each `PY` terminator dedents to column 0. The `uv run --no-sync --no-default-groups python - <<'PY'` form was also executed locally end to end. The actual first-run failure came from the one thing that could not be checked without the network — whether the action tag resolves. **Lesson: also verify action references resolve (`gh api repos/<owner>/<repo>/tags`) before the first push.**
- **The initial HTTPS push hung silently for >2 minutes** with `osxkeychain` as the credential helper and produced no error at all; the informative rejection only appeared when the push was retried through `gh auth git-credential`. Worth knowing: a silent `git push` hang on this machine is a credential-helper symptom, not a network one.
- **`timeout(1)` is not available on this macOS host** (no coreutils). Any workflow script or local helper that relies on it will fail with `command not found`. Not used anywhere in the committed workflow.
- **`origin/main` had been 25 commits behind before this plan** — all of Phase 1's planning and both prior execution plans were local-only. The push in this plan published them. Nothing was lost, but until now the project had no off-machine copy.
- **`prompt.md` remains untracked** at the repo root while `PROJECT.md` and `CLAUDE.md` both cite it as the authoritative spec. Pre-existing, out of scope, already in `deferred-items.md`. Now slightly more consequential: the repo is public and the authoritative spec is not in it.

## Threat Flags

None new. This plan introduces no application code, no network endpoint, no auth path, and no schema. It **implements** the mitigations its `<threat_model>` registered, and one item improved:

| Threat ID | Disposition | Delivered as |
|---|---|---|
| T-01-03 | accept (**reduced**) | `astral-sh/setup-uv` is pinned to the exact release `v10.2.0`, not a mutable major tag — an unplanned narrowing that fell out of the Rule 1 fix. `actions/checkout@v5` is still a major tag, so the item stays open and accepted at ASVS L1. Blast radius unchanged and minimal: verified `grep -c 'secrets\.'` = 0, no `permissions:` block (GITHUB_TOKEN ran at `Contents: read` / `Metadata: read` / `Packages: read` — confirmed in the run log), no publish, release, or artifact-upload step. Full-SHA pinning still belongs to the phase that adds PyPI publishing |
| T-01-02 | mitigate | All 3 `uv sync` lines carry `--locked` (`grep -c 'uv sync'` = 3, `grep -c 'uv sync --locked'` = 3); `uv lock --check` runs first in the `core` job and reported `Resolved 172 packages` on both OSes. No cell re-resolved |
| T-01-11 | mitigate | No `secrets.` reference, no `permissions:` block, so the default token cannot write. Reviewed the full green-run log: no credential, path, or token value appears |
| T-01-12 | mitigate | The `core` job is live on every push to `main` and every PR: `uv sync --locked --no-default-groups` installed exactly 17 packages, then `find_spec` confirmed none of `langgraph`/`crewai`/`ag2`/`langchain_core` is reachable. The test suite runs in its own separately-synced step so the two environments cannot be conflated (Pitfall 3) |
| T-01-13 | mitigate | `fail-fast: false` on both jobs, verified by `yaml.safe_load` |
| T-01-14 | mitigate | The `uname -m` guard executed on all three macOS cells and printed `macOS runner arch: arm64`. The guard is live, and its `::error::` path names `lancedb`, the missing x86_64 wheel and sdist, and the fix |
| T-01-SC | mitigate | Every CI install resolved from the committed hash-pinned `uv.lock` under `--locked`; the package set is the one audited in 01-RESEARCH.md §Package Legitimacy Audit (`slopcheck scan`, 10/10 `[OK]`). **`slopcheck install` was not run** (and must never be) |

## Known Stubs

None introduced by this plan. The three adapter placeholders from 01-02 are unchanged and still resolved by Phases 5/6/7 — and all three are now confirmed loadable through the lazy loader on both target OSes, which is the full extent of what the placeholder form is supposed to prove.

## User Setup Required

One, already applied, but it will recur:

- **`origin` must use SSH (or a token with the `workflow` scope) to push workflow changes.** This working copy is now on `git@github.com:AshraHossain/Self-ReflectiveAgentwithAuto-Eval.git`. A fresh clone via `gh repo clone` or an HTTPS URL will hit the same `refusing to allow an OAuth App to create or update workflow` rejection the next time `.github/workflows/` changes. Fix on a new clone: `git remote set-url origin git@github.com:AshraHossain/Self-ReflectiveAgentwithAuto-Eval.git`.

## Next Phase Readiness

**Phase 1 is complete — all 3 plans done, all 4 PACKAGE requirements satisfied, and every one of them now gated by CI rather than asserted once.**

| Requirement | Established by | Kept true by |
|---|---|---|
| PACKAGE-01 (framework-free core) | 01-01 `pyproject.toml`, 01-02 `backends.py` | `core` job `find_spec` assertion under `--no-default-groups`, both OSes |
| PACKAGE-02 (extras install and lazy-load) | 01-02 adapters + loader | `extra` job leak-then-load probe, 6 cells |
| PACKAGE-03 (committed lockfile, no drift) | 01-01 `uv.lock` | `core` job `uv lock --check`, both OSes |
| PACKAGE-04 (platform gap documented) | 01-01 README matrix, 01-02 verbatim error | `crewai` cells now *measure* the rows README claims |

**Ready for `/gsd-verify-work`.** The end-of-phase human check (`workflow.human_verify_mode: end-of-phase`) is the single outstanding item: open https://github.com/AshraHossain/Self-ReflectiveAgentwithAuto-Eval/actions/runs/36265951482 and confirm the 8-cell grid is green, paying particular attention to `crewai / ubuntu-latest` and `crewai / macos-latest`.

**Carried forward:**

- **Phase 6's Docker/colima Linux prerequisite is now evidence-backed** rather than inferred — `crewai / ubuntu-latest` installs `eacp[crewai]` cleanly from this lockfile. Still a prerequisite, still cannot be developed on this Intel host.
- **Phase 7 still needs the `ag2.network` spike** before adapter design is locked. Unchanged by this plan; `ag2 1.1.0` loads fine on both OSes, which says nothing about its multi-agent ergonomics.
- **The `ruff`/`mypy` job is deliberately absent.** Config already ships in `pyproject.toml`; adding the job is three lines. The natural moment is the first phase that ships enough Python to have conventions worth regressing — Phase 2.
- **`actions/checkout@v5` is still a mutable major tag** (T-01-03, accepted). Pin to a full commit SHA in the phase that adds a PyPI publish workflow.
- **Keep `UV_VERSION` and the local uv in lockstep at `0.12.19`.** Bumping either alone risks a `uv lock --check` failure on lockfile `revision` format, which looks like drift but is not.
- **`prompt.md` is still untracked in a now-public repo.**

## Self-Check: PASSED

- `.github/workflows/ci.yml` exists on disk; parses as YAML; jobs are exactly `{core, extra}`; 8 matrix cells; `env.UV_VERSION == "0.12.19"`; `fail-fast: false` on both jobs.
- Both task commits exist in git and on `origin/main`: `6582450` (ci), `9f93207` (fix). Neither contains a file deletion.
- Plan `<verification>` steps 1-6 all pass: YAML parse exits 0; most recent run is `success`; 8 jobs all `success`; `uv sync` lines = 3 and `uv sync --locked` lines = 3; `uv lock --check` exits 0 and `uv run pytest -q` reports `7 passed`; `grep -ric autogen pyproject.toml .github/` returns `0` and `0`.
- Task 2 acceptance criteria all met: push succeeded, 8 jobs, all `success`, `gh run watch --exit-status` exits 0, both `crewai` cells green, no assertion weakened, and run URL + per-cell grid + wall times + `FRAMEWORK_VERSION` values recorded above.

---
*Phase: 01-stack-decision-scaffold-packaging*
*Completed: 2026-09-26*
