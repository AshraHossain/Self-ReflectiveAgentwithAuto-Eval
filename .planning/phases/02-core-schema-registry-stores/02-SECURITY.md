---
phase: "02"
slug: "core-schema-registry-stores"
status: verified
threats_open: 0
asvs_level: 1
created: "2026-10-02"
---

# Phase 02 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `eacp.policy.load_yaml_mapping` / `load_policy_file` | The phase's only trust boundary — untrusted YAML bytes (policy file content) become a typed, validated `Policy` object. This is the single PyYAML entry point in `src/`. | Policy YAML text → validated `Policy` object or `PolicyError` |
| `eacp.registry.register_workflow` | A caller-supplied entrypoint name, backend name, and policy requirement set are checked against process-local allowlists before a workflow is registered. | Workflow/Policy objects → registered state or `ValueError`/`CapabilityError` |
| `eacp.store.SQLiteRunStore` | Run-history records cross into persistent SQLite storage on local disk. | `Run`/`Step` dataclasses → SQLite rows, and back |

---

## Threat Register

Built from the `<threat_model>` blocks in `02-01-PLAN.md`, `02-02-PLAN.md`, and `02-03-PLAN.md` (all three parseable — `register_authored_at_plan_time: true`). Verified by `gsd-security-auditor` against HEAD `1d269f1`, using 28 threat-gating tests plus independent throwaway probes, not by trusting the SUMMARYs' self-reported dispositions.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-02-01 | Tampering | `load_yaml_mapping` / `_StrictLoader` | high | mitigate | `_StrictLoader` compares constructed mapping keys and raises on a repeat, closing the limit-override primitive `extra="forbid"` cannot see (PyYAML collapses duplicates before pydantic runs). Verified against a plain duplicate, an aliased key, a nested duplicate, and a YAML merge-key (`<<`) override attempt — all four rejected. | CLOSED |
| T-02-02 | Denial of Service | `load_yaml_mapping` byte cap | medium | mitigate (partial scope — see note) | `MAX_POLICY_BYTES = 64 * 1024` checked against UTF-8 byte length before the parser runs. Verified: a 65,539-byte multi-byte-character document is rejected on byte count, not character count; an exactly-65,536-byte document passes the cap; the parser is never invoked when the cap is exceeded. | CLOSED |
| T-02-03 | Elevation of Privilege / RCE | every PyYAML call site in `src/` | high | mitigate | `_StrictLoader` (a `SafeLoader` subclass) is the package's single YAML entry point — verified no `safe_load`/`unsafe_load`/`full_load`/`FullLoader`/`UnsafeLoader`/bare `yaml.Loader`/`load_all`/`CLoader` exists anywhere in `src/` outside comments. `!!python/object/apply`, `!!python/name`, `!!python/object/new`, and `!!python/module` tags all rejected. | CLOSED |
| T-02-04 | Elevation of Privilege | `registry.py` import surface | high | mitigate | `registry.py` contains zero `importlib`/`__import__`/`exec`/`eval` calls (AST-verified). Entrypoints are dict lookups only. Adapters are reached only through `backends.load_backend_module`, which checks its allowlist before calling `import_module`. The AST gate was specifically rewritten mid-review after an earlier version false-positived on `re.compile` — re-verified against 11 fixtures before this phase's Wave 2 was dispatched. | CLOSED |
| T-02-05 | Tampering | `registry._ENTRYPOINTS` re-registration | medium | mitigate | `register_entrypoint` raises `DuplicateEntrypointError` on a name already registered; the original callable is confirmed to still resolve afterward. | CLOSED |
| T-02-06 | Tampering | `store.py` SQL construction | high | mitigate | AST walk found 10 `execute`/`executescript` calls; none receives an f-string, `%`-format, string concatenation, or `.format()`. The one built statement joins three constant strings only. Every value is a bound parameter. | CLOSED |
| T-02-07 | Repudiation | `policy_hash` canonicalization | high | mitigate | Canonical form is `json.dumps(dict, sort_keys=True, separators=(",", ":"))` — never `model_dump_json()` (absent anywhere in `src/`). Every collection field is `list[...]`, sorted/deduped by a validator (never `set[...]`). `test_hash_is_stable_across_processes` runs four real subprocesses with different `PYTHONHASHSEED` values. | CLOSED |
| T-02-08 | Repudiation | `policy_hash` payload key set | medium | mitigate | `test_hashed_key_set_is_pinned` pins the hashed field set against an explicit literal — fails both when a field is added to `Policy` and when a field moves into the excluded identity set. | CLOSED |
| T-02-09 | Information Disclosure | `PolicyError` message text | low | mitigate | Errors render with `include_url=False`, never render rejected `input`, and surface only `OSError.strerror` on file errors — no interpreter or environment paths in any message. | CLOSED |
| T-02-10 | Denial of Service | `store.list_runs` query limit | low | mitigate | `MAX_LIST_LIMIT = 1000`; requested limit clamped via `min(max(limit, 1), MAX_LIST_LIMIT)`. Verified against `10**9`, `2`, `0`, and `-5`. | CLOSED |
| T-02-11 | Information Disclosure | `runs.db` file permissions | medium | mitigate | DB file created via `touch(mode=0o600)` then `chmod(0o600)`, both before the first connection — verified under `umask 022` and against a pre-existing `0644` file. All of `runs.db`, `-wal`, and `-shm` end at `0600`. | CLOSED |
| T-02-12 | Spoofing | adapter `CAPABILITIES` declarations | medium | **transfer** → Phase 7 / CONFORM-01 | An adapter can declare `durable_approval` it does not actually deliver; nothing in Phase 2 can verify this, since no adapter executes a real workflow until Phase 5+. Transfer is legitimate, not a dodge — confirmed the three adapter placeholders contain no executable logic, only `BACKEND`/`FRAMEWORK_VERSION`/`CAPABILITIES`. Bounded now by `registry.py`'s `KNOWN_CAPABILITIES` check (catches an invented capability name, not a false claim of a real one). **Carried forward:** added as ROADMAP.md Phase 7 success criterion 4, so the obligation is visible to the Phase 7 planner rather than living only in `registry.py`'s docstring. | TRANSFERRED |
| T-02-13 | Tampering | `register_workflow` id re-registration | medium | mitigate | Raises on a workflow id already registered; the write to `_WORKFLOWS` happens only after every gate has passed, so a rejected registration changes nothing. Distinct from T-02-05 (a different map — entrypoints vs. workflow ids). | CLOSED |
| T-02-14 | Repudiation | `register_workflow` policy/workflow id mismatch | medium | mitigate | Raises when `policy.policy_id != workflow.policy_id`, preventing a run record from pinning a hash from a policy the workflow doesn't name. **Carry-forward note:** `_WORKFLOWS` stores only the `Workflow`, not the `Policy` — when Phase 4's run path pins `policy_hash` (POLICY-04, still pending pending the audit log), it must re-bind id↔hash at that point rather than assume this registration-time check still holds. | CLOSED |
| T-02-SC | Tampering (supply chain) | dependency lockfile | high | mitigate | `uv.lock` unchanged across all of Phase 2's commits; the phase's one `pyproject.toml` change (tool config only — `filterwarnings`, mypy overrides) touches no dependency table. `uv lock --check` passes. The only non-stdlib imports this phase adds are `pydantic` and `yaml`, both already locked from Phase 1. Appears once per plan (shared supply-chain threat, not three separate threats) — intentional, not a collision. | CLOSED |

*Status: open · closed · transferred — below `high` (block_on) threshold is non-blocking; nothing here is below threshold, every row was carried to full disposition.*
*Severity: critical > high > medium > low.*
*Disposition: mitigate (implementation verified) · accept (none this phase) · transfer (documented, bounded, owning phase named).*

---

## Accepted Risks Log

No accepted risks this phase. T-02-02's partial-scope mitigation (see note below) was a plan-time reasoned severity call, not an acceptance of an otherwise-closeable risk — closing it fully is not possible without PyYAML-level node-count limiting, which does not exist in the library.

**Note on T-02-02's scope:** the 64KB byte cap bounds input size, not how far YAML anchors/aliases can expand within that cap (02-RESEARCH.md measured 220 bytes → 531,441 nodes in 0.06s under `safe_load`, before this cap existed). A code review during this phase (`02-REVIEW-DISPOSITION.md`, finding WR-01) re-raised this and confirmed it is not a new gap — it is exactly what the plan-time register already disclosed ("blocks code execution but not amplification"), with severity reasoned as low/medium because v1 policy files are locally authored, not adversarial network input. This framing is preserved here deliberately rather than rounded up to "fully closed."

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-02 | 15 | 14 mitigated + 1 transferred | 0 | gsd-security-auditor (opus), verified against HEAD `1d269f1` with 28 threat-gating tests + independent probes |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log (none; T-02-02's partial scope documented above instead)
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-02
