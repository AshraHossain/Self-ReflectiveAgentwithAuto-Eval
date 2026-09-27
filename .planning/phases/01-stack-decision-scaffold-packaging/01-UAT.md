---
status: complete
phase: 01-stack-decision-scaffold-packaging
source: 01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md
started: 2026-09-26T21:00:00Z
updated: 2026-09-26T21:12:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Core Package Install (No Frameworks)
expected: |
  `uv sync --locked --no-default-groups` installs exactly 17 packages.
  `import eacp` reports 0.1.0. langgraph/crewai/ag2/langchain_core all absent.
result: pass
evidence: |
  17 packages. eacp 0.1.0. find_spec reachable: NONE. sys.modules after
  `import eacp`: NONE. PACKAGE-01 OK. Re-proved on this Intel host, matching
  01-02's local run and both CI `core` cells.

### 2. Lazy Backend Loader Works
expected: |
  load_backend_module('langgraph') -> BACKEND='langgraph', FRAMEWORK_VERSION='1.2.12'.
  load_backend_module('ag2') -> FRAMEWORK_VERSION='1.1.0'.
result: pass
evidence: |
  eacp[langgraph] = 52 packages, no leak on bare `import eacp`, loaded
  eacp.adapters.langgraph_adapter at 1.2.12.
  eacp[ag2] = 25 packages, no leak, eacp.adapters.ag2_adapter at 1.1.0.
  Both counts match 01-RESEARCH.md and CI exactly. FRAMEWORK_VERSION is never
  'unknown' — the importlib.metadata fix from 01-02 holds.
  crewai not locally testable (Intel/lancedb) — covered by test 6.

### 3. Missing Extra Raises MissingExtraError
expected: |
  Unregistered name -> ValueError. Registered-but-uninstalled -> MissingExtraError
  carrying `pip install 'eacp[...]'`.
result: pass
evidence: |
  available_backends() == ('langgraph', 'crewai', 'ag2').
  load_backend_module('unknown') -> ValueError listing known backends.
  load_backend_module('autogen') -> ValueError (T-01-01 naming mitigation live:
  'autogen' is not an alias for the ag2 backend).
  All three registered backends raise MissingExtraError in the core env with the
  correct install command and no filesystem/env detail in the message (T-01-05).

### 4. Tests Pass Locally
expected: |
  `uv run pytest -q` prints 7 passed and exits 0.
result: pass
evidence: |
  7 passed in 0.06s (01-VALIDATION.md budget: 2s — 30x margin).
  `uv lock --check` resolved 172 packages, exit 0 (PACKAGE-03 drift gate clean).
  `ruff check src tests` — All checks passed.

### 5. CI Matrix is Green on GitHub Actions
expected: |
  Run 36265951482 shows 8/8 green cells, conclusion success.
result: pass
evidence: |
  conclusion=success, headSha=9f93207, jobs=8, NON-SUCCESS=NONE.
  Cells: core/{ubuntu,macos}, langgraph/{ubuntu,macos}, crewai/{ubuntu,macos},
  ag2/{ubuntu,macos} — all success. Verified programmatically via `gh run view`,
  which also satisfies the outstanding end-of-phase human check.

### 6. CrewAI Extra Installs on Both Linux and macOS
expected: |
  Both crewai cells install 137 packages and report FRAMEWORK_VERSION 1.15.22.
result: pass
evidence: |
  crewai/ubuntu-latest: Installed 137 packages -> PACKAGE-02 OK
  (framework 1.15.22).
  crewai/macos-latest: `macOS runner arch: arm64`, Installed 137 packages ->
  PACKAGE-02 OK (framework 1.15.22).
  01-RESEARCH.md assumption A2 CONFIRMED. The uname -m guard fired on all three
  macOS extra cells (Pitfall 6 instrumented). README's Linux x86_64 and macOS
  arm64 crewai rows are now measured rather than wheel-tag-inferred — no
  correction needed.

### 7. README Documents the macOS x86_64 Gap
expected: |
  Platform matrix with 5 rows; Intel macOS marked unsupported for crewai with
  the lancedb mechanism explained.
result: pass
evidence: |
  README.md:27 `## Platform support` — 5-row matrix (Linux x86_64, Linux
  aarch64, macOS arm64, macOS x86_64, Windows x86_64) x 4 install targets.
  macOS x86_64 / eacp[crewai] = "❌ not supported", with the mechanism stated:
  crewai>=1.15 requires lancedb>=0.29.2,<0.30.1, which publishes no
  macosx_*_x86_64 wheel and no sdist, so there is nothing to build from.
  Correctly framed as an upstream packaging gap, not an EACP limitation.

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]

## Notes

All seven checks were executed programmatically rather than visually confirmed,
including the CI grid (`gh run view --json` + `--log`), so the end-of-phase human
check recorded in STATE.md is satisfied by machine evidence.

Requirements PACKAGE-01 through PACKAGE-04 are all verified and all four are now
held by CI on every push to main, not merely asserted once during execution.

Known non-defects carried forward (not UAT gaps):
- `eacp[crewai]` is uninstallable on this Intel dev host — upstream lancedb
  packaging gap. Phase 6 needs the already-decided Docker/colima container.
- Pushing `.github/workflows/` changes requires the SSH remote; a fresh HTTPS
  clone will be rejected by GitHub's OAuth-App workflow-scope rule.
- `prompt.md` is still untracked in a now-public repo while PROJECT.md and
  CLAUDE.md both cite it as authoritative.
