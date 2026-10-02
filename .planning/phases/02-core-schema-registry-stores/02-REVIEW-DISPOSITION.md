---
phase: 02-core-schema-registry-stores
review: 02-REVIEW.md
dispositioned: 2026-10-02
---

# Phase 2 Review Disposition

| ID | Severity | Summary | Disposition | Notes |
|----|----------|---------|-------------|-------|
| WR-01 | Warning | 64KB byte cap doesn't bound YAML anchor/alias node-count amplification within the cap | accepted | Not a new gap. T-02-02's own threat register entry already discloses this ("blocks code execution but not amplification"); 02-RESEARCH.md reasoned the severity as low because v1 policy files are locally authored, not adversarial network input. Carried forward into 02-SECURITY.md verbatim rather than rounded up to "fully closed." |
| WR-02 | Warning | `touch()` → `chmod()` → `connect()` in `SQLiteRunStore.__init__` is a TOCTOU window if the db path is ever attacker-influenced | accepted | Out of this phase's stated threat model — the store path is trusted/local for v1 (D-13). Worth re-checking if a later phase makes the path caller-supplied. |
| WR-03 | Warning | `Policy.version` had no floor, unlike every other numeric field | **fixed** | `Field(ge=1)` added, commit 533e864. Verified `version=0` now rejected; full suite (77 tests), mypy --strict, ruff all green after the change. |
| IN-01 | Info | `_PolicyId` (underscore-prefixed) imported across `policy.py`/`registry.py` | no_action | Deliberate internal type-alias sharing within a tightly-coupled package; not a public-API boundary violation. |
| IN-02 | Info | Reviewer's framing of how `registry.py` reaches adapter `CAPABILITIES` needed correction | resolved | Verified directly against source: `register_workflow` calls `load_backend_module()` — Phase 1's existing lazy-import chokepoint — only at call time, never at module scope. Not AST parsing (that's test-suite-only, for T-02-04's gate). No code defect; this was a misstatement in the review prompt, corrected during verification. |
| IN-03 | Info | Registry gate 2 (backend-name check) is reachable only via non-Literal construction paths | no_action | Deliberate defense-in-depth per `registry.py`'s own docstring — keeps "unknown backend" distinguishable from "extra not installed" if the `Literal` type is ever bypassed (e.g. `model_construct`). |

**Outcome:** 0 critical, 0 blocking. 1 of 3 warnings fixed; 2 accepted as already-disclosed, already-scoped residuals carried into the security audit with their original honest framing intact.
