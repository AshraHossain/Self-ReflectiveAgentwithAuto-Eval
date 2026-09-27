---
phase: 01-stack-decision-scaffold-packaging
status: secured
asvs_level: 1
block_on: high
threats_total: 16
threats_closed: 16
threats_open: 0
accepted_risks: 2
register_authored_at_plan_time: true
audited: 2026-09-26
method: direct code verification (no auditor subagent)
---

# Phase 1 Security Verification

**threats_open: 0.** Every threat registered across the three plan-time
`<threat_model>` blocks has been verified against the implementation, not
against the summaries' self-reported dispositions.

## Method

The register was built from the `<threat_model>` blocks in `01-01-PLAN.md`,
`01-02-PLAN.md` and `01-03-PLAN.md` (all three parseable, so
`register_authored_at_plan_time: true`). Rather than accept each SUMMARY's
"delivered as" claim, every `mitigate` disposition was re-checked directly
against `pyproject.toml`, `src/eacp/`, `tests/`, `uv.lock` and
`.github/workflows/ci.yml` by a scripted audit — 40 assertions, 0 failures.

Phase 1 ships no application code: no network listener, no request handler, no
auth path, no persistence, no cryptography, no user-input parser. Its entire
attack surface is the software supply chain plus one string→import resolver.
The register reflects that, and a retroactive STRIDE sweep was therefore not
warranted.

## Threat Register

| ID | Category | Component | Disposition | Status | Evidence |
|----|----------|-----------|-------------|--------|----------|
| T-01-01 | Spoofing / Tampering | `autogen`/`pyautogen`/`autogen-agentchat`/`ag2` four-way namespace | mitigate | CLOSED | `grep -ic autogen pyproject.toml` = 0; no adapter filename matches `autogen`; `ag2>=1.1,<2` exact pin; `"ag2"` key in `_BACKENDS`; `test_no_adapter_is_named_autogen` gates it; `load_backend_module("autogen")` → `ValueError` (executed) |
| T-01-02 | Tampering | 172 transitive packages | mitigate | CLOSED | `uv.lock` carries **2016** `sha256` hashes; `uv lock --check` exit 0; all 3 `uv sync` lines in CI carry `--locked` (3 of 3); upper bounds `<2`, `<1.3`, `<2.13` all present |
| T-01-03a | Tampering | `hatchling>=1.27` build backend | mitigate | CLOSED | `hatchling>=1.27` from PyPI, hash-verified in lock; `tool.hatch.build.hooks` count = 0 (no custom hook) |
| T-01-03b | Tampering / EoP | `actions/checkout@v5`, `astral-sh/setup-uv` mutable tags | **accept** | CLOSED (accepted) | `setup-uv` narrowed to exact `v10.2.0`; `checkout@v5` remains a major tag. Blast radius verified minimal: `secrets.` count = 0, no `permissions:` block, no publish/release/artifact step. See Accepted Risks. |
| T-01-04a | Information Disclosure | `[project] authors` in published metadata | mitigate | CLOSED | `authors = [{ name = "Ashrafuzzaman M Hossain" }]` — no `email` key (AST-checked) |
| T-01-04b | Tampering / EoP | `load_backend_module` → `importlib.import_module` | mitigate | CLOSED | AST-verified: exactly **1** real `import_module` call site (line 41); `_BACKENDS[...]` lookup at line 34 precedes it; `import_module` receives `module_path` (from the allowlist tuple), **not** the caller's `backend` parameter. Caller input can only ever be a dict key. |
| T-01-05 | Information Disclosure | `MissingExtraError` message text | mitigate | CLOSED | No `os.environ`, `sys.prefix`, `sys.executable`, `__file__`, `getcwd` or `sys.path` token anywhere in `backends.py` + `errors.py`; observed messages carry only package and extra names |
| T-01-06 | Elevation of Privilege | Dev tooling reaching a user environment | mitigate | CLOSED | PEP 735 `[dependency-groups]` present; no `dev` key under `[project.optional-dependencies]` (regex-checked), so `pip install eacp[dev]` cannot resolve |
| T-01-07 | Tampering | Host uv vs CI-pinned uv producing divergent lock revisions | mitigate | CLOSED | local `uv` = `0.12.19`; CI `UV_VERSION` = `0.12.19`; `uv.lock` `revision = 3`. All three agree. |
| T-01-08 | Tampering | Error handling masking a real defect (Pitfall 2) | mitigate | CLOSED | `framework_root` compared against `exc.name` root before translation; bare `raise` re-raises unchanged on mismatch. Demonstrated in 01-02 with a genuinely broken internal import. |
| T-01-09 | Spoofing | Stale global `crewai 1.9.3` satisfying a presence check | mitigate | CLOSED | Tests assert via `importlib.util.find_spec` inside the venv; CI probes run `--no-default-groups`; every local probe ran under `uv run --no-sync` |
| T-01-10 | Tampering | Framework code executed at import during adapter load | **accept** | CLOSED (accepted) | `langgraph`, `langchain-core`, `langgraph-checkpoint-sqlite`, `ag2` all `[OK]` in the `slopcheck scan` audit (10/10, 0 `[SLOP]`, 0 `[SUS]`) and hash-verified on install. See Accepted Risks. |
| T-01-11 | Information Disclosure | CI logs | mitigate | CLOSED | `grep -c 'secrets\.'` = 0; no `permissions:` block, so the default token cannot write. Green-run log reviewed: no credential, path or token value present. |
| T-01-12 | Tampering | PACKAGE-01 silently regressing in a later phase | mitigate | CLOSED | `core` job runs `uv sync --locked --no-default-groups` then a `find_spec` assertion naming PACKAGE-01, on every push to `main` and every PR. Verified live: 17 packages, 0 frameworks reachable, both OSes. |
| T-01-13 | Denial of Service (self-inflicted) | A CrewAI nightly break cancelling the whole matrix | mitigate | CLOSED | `fail-fast: false` present exactly twice (both jobs) |
| T-01-14 | Spoofing | `macos-latest` floating to an Intel runner | mitigate | CLOSED | `uname -m` guard present, emits `::error::`, and names `lancedb` as the cause. Fired on all 3 macOS extra cells reporting `arm64`. |
| T-01-SC | Tampering | Supply-chain installs (local + CI) | mitigate | CLOSED | Every install resolved from the committed hash-pinned lock under `--locked`; `grep -rn 'slopcheck install'` across shell/yml/py = 0 occurrences |

## Accepted Risks

### T-01-03b — CI actions referenced by a mutable major tag

`actions/checkout@v5` resolves through a tag the upstream owner can move. A
compromised tag would execute arbitrary code on the runner.

**Accepted at ASVS L1** because the blast radius is verifiably empty: this
workflow reads no secret (`secrets.` count 0), declares no `permissions:`
block, and has no publish, release or artifact-upload step — a compromised
action executes in a throwaway runner with nothing to exfiltrate and nothing to
write. The correct control is full-commit-SHA pinning, and it is deferred to the
phase that adds a PyPI publish workflow, which is the point at which this
becomes materially dangerous.

Partially reduced during 01-03: `astral-sh/setup-uv` is now pinned to the exact
release `v10.2.0` (a side effect of fixing the non-existent `@v10` tag), so only
`checkout` remains on a major tag.

### T-01-10 — Third-party framework code executes at adapter import

`load_backend_module` imports `langgraph` / `crewai` / `ag2`, which runs their
module-scope code. This is irreducible: importing the framework is the entire
purpose of an adapter.

**Accepted at ASVS L1.** All four relevant distributions are `[OK]` in the
package-legitimacy audit, every install is hash-verified from `uv.lock`, and no
sandboxing control is available or expected at this level.

## Audit Trail

### Security Audit 2026-09-26

| Metric | Count |
|--------|-------|
| Threats found | 16 |
| Closed (mitigated) | 14 |
| Closed (accepted) | 2 |
| Open | 0 |
| Assertions executed | 40 |
| Assertion failures | 0 |

**Audit script:** `audit_phase1.sh` (session scratchpad — not committed; it
hardcodes an absolute path and is a one-off verification aid, not a CI gate).
Every check it performs is either already enforced by `tests/test_packaging.py`
and the CI matrix, or is a property of a committed file that can be re-derived
by inspection.

## Findings Beyond the Register

Two issues surfaced during verification. Neither is a vulnerability.

1. **Threat-ID collision across plans (register hygiene).** `T-01-03` and
   `T-01-04` are each reused for two *different* threats in different plans —
   `T-01-03` is the hatchling build backend in 01-01 but mutable action tags in
   01-03; `T-01-04` is author metadata disclosure in 01-01 but the
   import-allowlist in 01-02. Verifying "T-01-04" against one plan would leave
   the other unverified while appearing covered. Split here into `a`/`b`
   suffixes. **Later phases should allocate threat IDs from a single
   phase-wide sequence, not per-plan.**

2. **The first audit script reported a false pass.** Its Python-based checks
   printed `FAIL` but did not propagate to the exit code, so it printed
   `0 failures` while two checks had failed. Both were themselves false
   positives (a char-offset heuristic counting the word `import_module` inside a
   comment as a call site), but the exit-code bug would have hidden a real
   failure. Fixed by routing Python checks through a wrapper that propagates
   status, and by replacing the offset heuristic with AST analysis — which is
   what produced the decisive T-01-04b evidence that the caller's parameter
   never reaches `import_module`.
