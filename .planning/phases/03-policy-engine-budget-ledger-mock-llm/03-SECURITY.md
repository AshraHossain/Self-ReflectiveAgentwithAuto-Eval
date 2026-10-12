---
phase: "03"
slug: "policy-engine-budget-ledger-mock-llm"
status: verified
threats_open: 0
asvs_level: 1
created: "2026-10-09"
---

# Phase 03 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Policy YAML bytes → `Policy.max_steps` / `Policy.model_prices` | Phase 2's trust boundary, extended to two more enforceable fields. | Policy YAML → validated `Policy` (now 9 enforceable fields) |
| `Usage` readings → `engine.cost_of` / ledger accounting | Usage counts arrive from a provider (Phase 5-7) or the scripted mock (this phase); the type makes "no reading" and "a zero reading" impossible to confuse. | `Usage` dataclass → cost/token accounting |
| `decide()`'s return value → every caller | `Decision` is the only channel through which an allow/deny is communicated — never a bare boolean. | `Decision` dataclass → ledger / future audit log |
| Concurrent processes/threads → the same `ledger.db` | Multiple runs reach the same file at once; transaction style decides whether the budget is real or decorative under real concurrency. | SQLite reads/writes under `BEGIN IMMEDIATE` |
| Adapter-supplied `policy_id`/`run_id`/`call_key`/`model` → SQL statement text | These strings originate above the ledger and, from Phase 5 onward, come from adapter-chosen identifiers. | Bound SQL parameters only |
| `ledger.db` on disk | The project's second persistent artifact (daily spend, run totals, reservation history). | SQLite file, WAL + sidecars |
| `MockLLM`'s scripted output → the ledger's accounting | Stands in for every real provider response Phases 5-7 will wire in. | Scripted `MockTurn`/`Usage` → `admit()`/`reconcile()` |

---

## Threat Register

Built from the `<threat_model>` blocks in `03-01-PLAN.md`, `03-02-PLAN.md`, and `03-03-PLAN.md`. Verified by `gsd-security-auditor` against HEAD `fa00e1c` (post-review-fix commit), using live reproduction of the code-review's exact repro commands plus direct re-execution of the gating tests — not by trusting SUMMARY/REVIEW self-reports. Spot-re-verified by the orchestrator for T-03-08 and T-03-10 directly against source.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-03-01 | Tampering | `engine.Usage` | medium | mitigate | `Usage.__post_init__` rejects negative, bool, and None-mismatched-with-`usage_source` readings. Verified via `test_usage_rejects_negative_counts`, `test_usage_rejects_bool_counts`, and the two "requires" tests. | CLOSED |
| T-03-02 | Repudiation | `engine.cost_of` + `policy.ModelPrice` price quantization | medium | mitigate | `cost_of` always quantizes with `ROUND_CEILING`. **Scope note:** a second zero-cost path existed in `ModelPrice`'s own field validator (default `ROUND_HALF_EVEN`, not covered by the original plan-time mitigation) — found by code review as CR-01, fixed via a dedicated `_quantize_price(ROUND_CEILING)`. Reproduced fixed this audit: `$0.0000003/Mtok` now stores as `0.000001` and prices non-zero cost for 10M tokens, where it previously stored/priced exactly `$0`. | CLOSED |
| T-03-03 | Elevation of Privilege | `engine.decide` (LLM branch) | high | mitigate | An unpriced model denies with `rule == "model_prices"` before any cost arithmetic. Verified via `test_unpriced_model_is_denied`. | CLOSED |
| T-03-04 | Elevation of Privilege | `engine.decide` (tool branch) | high | mitigate | `allowed_tools: []` denies every tool (plain `in` on empty list); `forbidden_tools` checked first and wins. Verified via `test_empty_allowed_tools_denies_every_tool`, `test_forbidden_tools_beats_allowed_tools`. | CLOSED |
| T-03-05 | Repudiation | `policy_hash` payload key set | medium | mitigate | `max_steps`/`model_prices` added to the pinned hashed key set in the same task that added them to the schema (nine fields total, neither in `_IDENTITY_FIELDS`). Verified via `test_hashed_key_set_is_pinned`, `test_hash_is_content_addressed`. | CLOSED |
| T-03-06 | Tampering | `SQLiteBudgetLedger.admit` transaction boundary | high | mitigate | `isolation_level=None` + explicit `BEGIN IMMEDIATE` around the full read-decide-write sequence. Verified: static AST check (every `connect()` carries literal `isolation_level=None`) and a real 4-process contention test (`test_four_processes_race_to_the_cap`) re-run this audit — exactly 10 of 10 admitted. | CLOSED |
| T-03-07 | Tampering | every ledger SQL statement | high | mitigate | Every value is a bound parameter; no f-string/%-format/`.format()` reaches `execute`/`executescript` (AST-verified, re-run this audit, 0 violations). `test_policy_id_with_sql_metacharacters_is_inert` re-run — PASSED. | CLOSED |
| T-03-08 | Information Disclosure | `ledger.db`, `-wal`, `-shm` | medium | mitigate | Mode `0600` set before first connect (`touch(mode=0o600)` then `chmod(0o600)`, `ledger.py:145-146`). `test_ledger_file_is_not_world_readable` re-run with a connection held open — PASSED. Orchestrator re-confirmed both lines directly. | CLOSED |
| T-03-09 | Tampering | `reservations` replay / idempotency | medium | mitigate (partial scope — see Accepted Risks Log) | `(run_id, call_key)`-keyed short-circuit prevents double-charging on replay, in-flight or reconciled. Verified via `test_replayed_admit_is_not_charged_twice`. **Not covered:** request-consistency validation on a `call_key` collision (WR-02) and replayed-`Decision.observed` accuracy (WR-03) — both found by code review, accepted as residual risk, see below. | CLOSED (residual risk logged) |
| T-03-10 | Repudiation | `_tx()` error handling | low | mitigate | `ROLLBACK` issued only when `c.in_transaction` is true (`ledger.py:176`), preventing a misleading second error from masking the real `BEGIN IMMEDIATE` failure. Orchestrator re-confirmed directly in source. | CLOSED |
| T-03-11 | Denial of Service | runaway loop with `MISSING` or near-zero usage | medium | mitigate | `max_steps` checked first in `decide()`, independent of token/cost accounting. Verified via a real scripted loop with an exact call-count assertion (`test_runaway_mock_is_stopped_by_max_steps_independent_of_budget`), re-run this audit. | CLOSED |
| T-03-SC | Tampering (supply chain) | dependency lockfile | high | mitigate | No dependency table change since Phase 1's `432dcd5`; every task re-runs `uv lock --check` against the committed, hash-pinned lockfile. Re-verified this audit and again by the orchestrator: 172 packages resolve clean. Appears once per plan in the plan-time register (shared supply-chain threat) — collapsed to one row here, same convention as `02-SECURITY.md`. | CLOSED |

*Status: open · closed · transferred — below `high` (block_on) threshold is non-blocking; nothing here is below threshold or open — every row carried to full disposition.*
*Severity: critical > high > medium > low.*
*Disposition: mitigate (implementation verified) · accept (two residual gaps, see Accepted Risks Log) · transfer (none this phase).*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|--------------|------|
| WR-02 | T-03-09 | `admit()`'s replay short-circuit returns the existing reservation on a `(run_id, call_key)` hit with no validation that the replayed request matches the original. Exploitability requires a caller bug (a `call_key` reused across semantically different requests); current test suite uses deterministic, non-colliding keys. A correct fix needs either persisting enough of the original request to compare against, or re-running `decide()` on replay — real design work, not a one-line guard. Carried forward to Phase 4 (audit log) and Phase 5+ (adapters, which mint `call_key`s per node/call-index). | 03-REVIEW-DISPOSITION.md (2026-10-09) | 2026-10-09 |
| WR-03 | T-03-09 | A replayed `Decision.observed` for `max_cost_per_day` reports this single reservation's cost (`Decimal(row["cost"])`), not the cumulative daily spend a genuine `decide()` call reports (`state.spent_today + cost_of(...)`) — different numbers whenever another call happened the same day. Phase 3's SUMMARYs state Phase 4's audit log will read `Decision` directly, so this is a real correctness gap for that consumer, not a hypothetical one. Carried forward to Phase 4: either persist the real `observed`/`limit` at replay time, or mark replayed decisions as synthetic before Phase 4 builds against `Decision` assuming every instance came from a live `decide()` call. | 03-REVIEW-DISPOSITION.md (2026-10-09) | 2026-10-09 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|----------------|--------|------|--------|
| 2026-10-09 | 12 (+2 accepted residual risks) | 12 mitigated | 0 | gsd-security-auditor (sonnet), verified against HEAD `fa00e1c` with 125-test full suite re-run + 5 individually re-run gating tests + 3 live exploit reproductions (CR-01 fix, WR-01 fix, T-03-07 AST gate); T-03-08/T-03-10 spot-re-verified directly by the orchestrator |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log (WR-02, WR-03)
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-09
