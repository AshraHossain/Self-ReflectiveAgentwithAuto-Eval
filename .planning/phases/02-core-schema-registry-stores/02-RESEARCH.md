# Phase 2: Core Schema, Registry & Stores - Research

**Researched:** 2026-09-27
**Domain:** pydantic 2.12 strict schemas + canonical content hashing, PyYAML 6.0.3 safe deserialization, `typing.Protocol` store interfaces, stdlib `sqlite3` on CPython 3.12
**Confidence:** HIGH — every version-specific claim below was **executed** against this repo's own `.venv` (Python 3.12.13, pydantic 2.12.5, pydantic-core 2.41.5, PyYAML 6.0.3, SQLite 3.53.2) today. Nothing in the Standard Stack, Code Examples, or Pitfalls sections is from training memory; each carries the command output that produced it.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-06: The `RunStore` Protocol is synchronous.** `def write_run(...)`, not
  `async def`. Rationale: SQLite's stdlib driver is sync, so a sync Protocol matches the
  real I/O rather than wrapping it in a false async surface. CrewAI (sync hooks) and
  LangGraph call it directly with zero ceremony. **ag2 is the one that bridges** — its
  middleware is `async def` throughout, so the ag2 adapter wraps store calls in
  `asyncio.to_thread(...)`. That cost is one line per call site and is contained inside
  `ag2_adapter.py`.
  Rejected: an async Protocol, because CrewAI's sync hooks would have to drive an event
  loop to reach it, and `asyncio.run` inside a hook deadlocks when a loop is already
  running. Also rejected: shipping both a sync Protocol and an async wrapper — two
  surfaces and two test suites for a convenience the ag2 adapter expresses in one line.

- **D-07: Each adapter declares its own capabilities.** Every adapter module exports a
  `CAPABILITIES` constant alongside the `BACKEND` and `FRAMEWORK_VERSION` constants
  Phase 1 already established. The registry reads it through
  `eacp.backends.load_backend_module`.
  Rationale: the truth lives next to the code that implements it and cannot drift.
  Reuses the existing placeholder shape with no new pattern.
  Rejected: a central table in `registry.py` — readable offline, but an adapter could
  gain or lose a capability without the table noticing, which is exactly the silent
  divergence the AdapterCapabilities decision exists to prevent.

  **Known consequence, accepted:** reading a backend's capabilities requires importing
  its adapter, which requires that extra installed. So registering a LangGraph workflow
  without `eacp[langgraph]` fails with Phase 1's `MissingExtraError` ("install the
  extra") rather than a capability error. This is honest — you cannot run a backend you
  have not installed — but it means there is **no offline path to print the full
  capability matrix**. If docs later need that matrix, generate it in CI where all three
  extras are installed, not at runtime.

### Claude's Discretion (defaulted, not user-decided — change freely if research disagrees)

- **D-08: Policy schema is strict in both directions.** pydantic with
  `extra="forbid"` (forced by POLICY-01's success criterion), and every POLICY-02 limit
  field is **required with no default**. A policy omitting `max_cost_per_day` is invalid,
  not unlimited. Direction of safety: relaxing required→optional later is non-breaking;
  tightening is breaking.
- **D-09: The policy hash covers the canonicalized model, not raw YAML bytes.**
  Serialize the validated pydantic model to canonical JSON with sorted keys, then
  SHA-256. Open sub-questions for research: whether an absent optional field hashes
  identically to an explicit null, and whether `policy_id` itself is inside the hashed
  payload.
- **D-10: The entrypoint allowlist is explicit registration, mirroring `_BACKENDS`.**
  Allowlist lookup strictly before any resolution, so a caller-supplied string is never
  interpolated into an import target. Rejected: import-path prefix matching (bypassable)
  and Python entry-point groups (any installed package could inject one).

**Research verdict on the three discretionary defaults:** D-08 **confirmed with one
amendment** (model-level `strict=True` is wrong — see §Finding 2; use field-level
`StrictInt`). D-09 **confirmed and sharpened** (both open sub-questions answered below;
sorting keys is not optional — see §Finding 1). D-10 **confirmed unchanged**, and it
turns out to be the *only* design that survives WORKFLOW-01's "opaque pointer" wording —
see §Finding 5.

### Deferred Ideas (OUT OF SCOPE)

- **Offline capability-matrix rendering** — D-07's accepted consequence. If docs need a
  full matrix without installing all three extras, generate it in CI (where all extras
  are present) rather than adding a central runtime table.
- **Per-tenant policy scoping** — already deferred to v2 at requirements time.
- **A second store backend (Postgres)** — the Protocol makes it possible; v1 ships
  SQLite only, per PROJECT.md.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| POLICY-01 | Policy defined declaratively in YAML with a fixed field schema (no custom DSL), loaded via `yaml.safe_load` only | §Finding 3 (`safe_load`'s three silent failures + the ~12-line `_StrictLoader` that closes the worst one), §Code Example 1. Verified: unknown field → `extra_forbidden`, non-mapping root → `ValueError`, duplicate key → `ConstructorError`, `!!python/object/apply` → `ConstructorError`. All executed. |
| POLICY-02 | Schema includes max_tokens_per_run, max_cost_per_day, allowed_tools, forbidden_tools, required_approval_nodes, compliance_tags | §Standard Stack → field-type table. `StrictInt` for counters (blocks YAML `yes`→`1`), lax `Decimal` for money (accepts YAML `25.00`, rejects `True`), `list[str]` **never** `set[str]` (§Finding 1). |
| POLICY-04 | Every policy is content-hashed; the hash is pinned to every run record and every audit log entry | §Finding 1 + §Code Example 2. Verified: two YAML files differing in key order, list order, `policy_id`, `version`, and `25.00` vs `25.0` produce the **identical** SHA-256. The `runs` table carries `policy_hash` as a NOT NULL column. |
| WORKFLOW-01 | Workflow schema is id, name, description, backend_type, entrypoint, policy_id — entrypoint opaque, no nodes/agents/edges | §Finding 5. `backend_type` is a `Literal` single-sourced against `available_backends()` by test; `entrypoint` is an allowlist **key**, not a path. |
| WORKFLOW-02 | Registry validates entrypoint against an allowlist at registration time | §Finding 5 + §Code Example 3. Verified: `os.system` rejected by charset, unknown name rejected by lookup, re-registration rejected. Zero `import_module` calls in the registry. |
| WORKFLOW-03 | Registry fails loudly at registration if the backend adapter lacks a capability the policy requires | §Finding 4. Explicit `requires:` list (implicit derivation cannot express the only axis on which the three backends differ); vocabulary `{durable_approval, inline_approval}` for v1; one-line `set` difference check. |
| TRACE-03 | Run history persisted to a pluggable store, SQLite for v1 | §Finding 6 + §Code Example 4. Six-method `Protocol`, connection-per-call, WAL, `PRAGMA user_version` for migrations. Verified end to end: write run → 3 steps → finish → read back → filter → cross-thread read → FK violation → SQL-injection attempt. |
</phase_requirements>

---

## Project Constraints (from CLAUDE.md)

| Directive | Source | Phase 2 implication |
|-----------|--------|---------------------|
| Python 3.11+ with type hints | Constraints | Everything here is `mypy --strict` clean. Note `requires-python = ">=3.11,<3.14"` — **do not use `uuid.uuid7`** (3.14+ only, verified absent on 3.12) and **do not use PEP 695 `type` statements** if 3.11 must pass. `datetime.UTC` is available (3.11+, verified). |
| Dependencies must be real, pinned, current stable | Constraints | **Phase 2 adds zero new dependencies.** `pydantic`, `pyyaml` and stdlib `sqlite3`/`hashlib`/`json`/`uuid` cover the whole phase. See §Package Legitimacy Audit. |
| Runnable without paid keys | Constraints | No LLM surface in this phase. |
| Persistence: SQLite, simple + pluggable | Constraints | Directly this phase. "Pluggable" is satisfied by the `Protocol`, not by an ORM — reconfirmed. |
| Scope discipline | Constraints | Do **not** build the approval store, audit log, or budget ledger here. They are Phase 3/4 and want their own Protocols. |
| GSD Workflow Enforcement | GSD section | Execution must run under `/gsd-execute-phase`. |
| CLAUDE.md "Conventions" section is empty | Conventions | Phase 2 establishes the project's *core-code* conventions (Protocol-over-ABC, dataclass-for-internal / pydantic-at-the-boundary, canonical-hash helper). Worth writing back at phase end. |

⚠️ **CLAUDE.md staleness note:** its stack table pins `pydantic 2.12.5`, which is exactly what is installed — confirmed, not stale. Its `opentelemetry-*` entry says `1.44.0`; the venv actually resolves `opentelemetry-semantic-conventions 0.66b0`. Irrelevant to Phase 2 (nothing here imports OTel) but relevant to Phase 5 — see §State of the Art.

---

## Summary

This phase is small — roughly 300 lines of core Python across four modules — and I was able to build and run the entire proposed design end to end today. The prescriptive answer is: **pydantic at the YAML trust boundary, frozen `@dataclass` for internal records, `json.dumps(model.model_dump(mode="json"), sort_keys=True)` for the content hash, a plain name→callable dict for the entrypoint allowlist, and a six-method `Protocol` over a connection-per-call SQLite store.** No new dependencies, no ORM, no ABC, no `@runtime_checkable`.

**Three findings change the design as it was defaulted, and the planner must act on all three.**

First, **`model_dump_json()` does not sort keys and pydantic 2.12.5 offers no option that does** — verified: `sort_keys` is absent from the parameter lists of both `BaseModel.model_dump_json` and `pydantic_core.to_json`. It emits keys in *field-declaration order*, so a developer reorganising the `Policy` class body silently changes every policy hash in the project's history. Worse, if `compliance_tags` is typed `set[str]` — the natural choice — the serialized order is genuinely nondeterministic across processes: three runs of the same code produced `["pci","iso27001","hipaa","soc2","gdpr"]`, `["pci","soc2","hipaa","iso27001","gdpr"]`, `["pci","hipaa","gdpr","iso27001","soc2"]`. Either of these alone silently defeats POLICY-04's entire reason for existing. D-09's "sorted-key JSON" instinct is correct and is **load-bearing, not cosmetic**; it must be paired with `list[str]` fields normalized to sorted order by a validator.

Second, **`yaml.safe_load` silently accepts a duplicate key and keeps the last one.** `max_tokens_per_run: 100` followed by `max_tokens_per_run: 999999` parses to `999999` with no error and no warning — and because PyYAML collapses the duplicate *before* pydantic ever sees the mapping, `extra="forbid"` cannot catch it. In a governance tool, that is a limit-override primitive hiding in the loader. The fix is a ~12-line `SafeLoader` subclass; it is not optional and it belongs in the same task as the schema. (Related: a 220-byte alias-expansion bomb expands to 531,441 nodes in 0.06s under `safe_load`, which blocks code execution but not amplification — a one-line byte cap closes it.)

Third, **`@runtime_checkable` is signature-blind and would give the `RunStore` Protocol false credibility.** Verified: `isinstance(Wrong(), RunStore)` returned `True` for a class whose methods have entirely wrong arities and return types, while `mypy --strict` caught the same class precisely on a one-line `_: RunStore = SQLiteRunStore(...)` assignment. Use the static probe; skip the decorator.

Everything else confirms the defaults. `policy_id` belongs **outside** the hashed payload (and so does `version`) — the content hash is what a content hash is everywhere else in this ecosystem: a git blob hash excludes the filename, an OCI digest excludes the tag, and OPA separates a bundle's `revision` from its content. Excluding both buys a real governance property: "did the rules actually change between v1 and v2?" becomes a string comparison. And the store's connection-per-call design costs a measured **1.2 ms per write** against a **161 µs** long-lived connection — an extra millisecond per run-history row, against LLM calls measured in seconds — in exchange for deleting the entire thread-safety problem that CREWAI-03 warns about and making Phase 4's cross-process `eacp approve` CLI correct by construction.

**Primary recommendation:** Build four core modules — `policy.py` (schema + loader + hash), `registry.py` (entrypoint allowlist + workflow model + capability gate), `capabilities.py` (the vocabulary), `store.py` (Protocol + `SQLiteRunStore`) — using §Code Examples 1–4 verbatim, and add `CAPABILITIES` to the three existing adapter placeholders. Plan `policy.py` and `store.py` as parallel tasks (they share nothing); `registry.py` depends on both.

---

## Architectural Responsibility Map

This phase has no request path. The meaningful decomposition is which module owns which guarantee.

| Capability | Primary Owner | Secondary Owner | Rationale |
|------------|--------------|-----------------|-----------|
| Turning untrusted YAML bytes into a typed object | `eacp/policy.py` (`_StrictLoader` + `Policy`) | — | The phase's only trust boundary. pydantic belongs here and **nowhere else** in this phase. |
| Producing a stable content identity for a policy | `eacp/policy.py` (`policy_hash`) | — | One function, one canonicalization rule. Splitting it across modules is how two subtly different canonical forms appear. |
| Declaring the capability vocabulary | `eacp/capabilities.py` | — | Core-only, framework-free. Both the adapters and the registry import it, so it cannot live in either. |
| Declaring what a backend actually provides | `eacp/adapters/<fw>_adapter.py` `CAPABILITIES` | — | D-07. Truth next to implementation. |
| Gating a registration on capability + entrypoint | `eacp/registry.py` | `eacp/backends.py` | The only module that couples the two halves; `backends.load_backend_module` remains the single import chokepoint. |
| Describing a run's persistence contract | `eacp/store.py` (`RunStore` Protocol) | — | Protocol only — no I/O, no SQL. This is what Phase 5/6/7 type against. |
| Persisting runs for v1 | `eacp/store.py` (`SQLiteRunStore`) | — | Same file is fine at this size; split only if a second backend lands (v2, deferred). |
| Keeping all of the above framework-free | `.github/workflows/ci.yml` `core` job | — | Already exists and already runs `uv sync --locked --no-default-groups` + `find_spec`, then `uv run pytest -q` with **no extras installed**. Phase 2 needs **no CI change** — success criterion 4 is enforced by infrastructure Phase 1 already shipped. |

---

## Standard Stack

**Phase 2 adds no dependencies.** Everything below is already in `[project] dependencies` or the stdlib. Versions are the *installed* versions in this repo's `.venv`, read today.

### Verified environment

```
$ .venv/bin/python -c "..."
python 3.12.13 (main, Mar  3 2026) [Clang 21.0.0]
pydantic 2.12.5     pydantic-core 2.41.5     pyyaml 6.0.3
sqlite3 module 2.6.0   lib 3.53.2   threadsafety 3
```
[VERIFIED: executed in `.venv` 2026-09-27]

### Core

| Library | Installed | Purpose in Phase 2 | Why standard |
|---------|-----------|--------------------|--------------|
| `pydantic` | **2.12.5** | `Policy` + `Workflow` validation at the YAML boundary | Already a core dep; `extra="forbid"` is exactly POLICY-01's success criterion. `<2.13` cap is crewai-forced, unchanged. |
| `PyYAML` | **6.0.3** | `yaml.safe_load` / `SafeLoader` subclass | POLICY-01 names it. Already a core dep. |
| `hashlib` (stdlib) | 3.12 | SHA-256 for POLICY-04 | No dependency. |
| `json` (stdlib) | 3.12 | **Canonicalization** — `sort_keys=True` is the piece pydantic cannot do (see §Finding 1) and `metrics`/`attributes` column encoding | No dependency. |
| `sqlite3` (stdlib) | lib **3.53.2** | `SQLiteRunStore` | PROJECT.md-locked. `threadsafety == 3` on this build. |
| `typing.Protocol` (stdlib) | 3.12 | `RunStore` pluggability | Structural typing — a second backend needs no inheritance. |
| `dataclasses` (stdlib) | 3.12 | `RunRecord` / `StepRecord` | See §Don't Hand-Roll for why these are *not* pydantic models. |
| `uuid` (stdlib) | 3.12 | `run_id = uuid.uuid4().hex` | `uuid.uuid7` is **not available on 3.12** (verified `hasattr(uuid,'uuid7') == False`); it lands in 3.14, which `requires-python = "<3.14"` excludes. |

### Field types for the POLICY-02 fields — the prescriptive table

| Field | **Use this** | **Not this** | Verified reason |
|-------|-------------|--------------|-----------------|
| `max_tokens_per_run` | `Annotated[StrictInt, Field(ge=1)]` | `int` | YAML `yes` → Python `True` → **lax `int` accepts it as `1`**. `StrictInt` rejects `True`, `"10"` and `10.0` (`int_type`). |
| `max_cost_per_day` | `Annotated[Decimal, Field(ge=0)]` + quantize validator | `float`; also **not** model-level `strict=True` | Lax `Decimal` accepts YAML `25` and `25.00`, and **already rejects `True`** (`decimal_type`). Model-level `strict=True` rejects a plain YAML int with `is_instance_of` — see §Finding 2. |
| `allowed_tools`, `forbidden_tools`, `required_approval_nodes`, `compliance_tags` | `list[str]` + a sort/dedupe validator | **`set[str]`** | `set[str]` serializes in nondeterministic order across processes. This is the single worst POLICY-04 trap. See §Finding 1. |
| `requires` | `list[Capability]` where `Capability = Literal[...]` | `list[str]` | A typo'd capability is rejected at load time with `literal_error` naming the field index, instead of silently never matching. |
| `policy_id` | `str` (+ a charset constraint) | — | Identity. **Excluded from the hash.** |
| `version` | `StrictInt` | — | Identity. **Excluded from the hash.** |

### Alternatives considered

| Instead of | Could use | Tradeoff |
|------------|-----------|----------|
| `json.dumps(..., sort_keys=True)` | `model_dump_json()` | **Rejected.** No `sort_keys` parameter exists in pydantic 2.12.5 (verified by `inspect.signature`), so key order follows field declaration order and a source-file refactor changes every hash. |
| `Decimal` + quantize | `Decimal` + `.normalize()` | **Rejected.** `Decimal("100").normalize()` → `Decimal('1E+2')`, which serializes as `"1E+2"`. Quantizing to a fixed exponent is the only stable normalization. |
| `Decimal` | `float` for money | Float is canonically serializable and adequate for a daily budget, but "money in float" in a governance reference implementation invites reviewer fire for no gain; `Decimal` costs one validator. |
| frozen `@dataclass` for `RunRecord` | `pydantic.BaseModel` | pydantic validation on every step-write buys nothing — the data is produced by our own adapters, not parsed from untrusted input. Keep pydantic at the boundary only. |
| `Protocol` + static probe | `abc.ABC` | ABC forces `SQLiteRunStore` to inherit, which makes third-party stores import `eacp` internals. Structural typing is the point of "pluggable". |
| `Protocol` (plain) | `@runtime_checkable` Protocol | **Rejected.** Signature-blind — see §Finding 7. |
| Connection-per-call | One connection + `check_same_thread=False` + a `Lock` | ~1 ms/write slower, but deletes thread-affinity, connection lifecycle, and cross-process coherence as concerns. See §Finding 6. |
| `PRAGMA user_version` | `alembic` / a migrations table | Alembic is a new dependency and a second config file for a schema that will change perhaps twice before v1 ships. |

**Installation:** none. `pyproject.toml` is unchanged by this phase.

---

## Package Legitimacy Audit

**This phase installs no external packages.** All four modules are built from packages already declared in `[project] dependencies` (Phase 1, already lock-pinned and hash-verified under `--locked`) plus the Python standard library.

| Package | Registry | Source Repo | Verdict | Disposition |
|---------|----------|-------------|---------|-------------|
| `pydantic` | PyPI (already pinned `>=2.11,<2.13`, resolves 2.12.5) | github.com/pydantic/pydantic | OK | Already approved in Phase 1; no change |
| `PyYAML` | PyPI (already pinned `>=6`, resolves 6.0.3) | github.com/yaml/pyyaml | OK | Already approved in Phase 1; no change |

**Packages removed due to [SLOP] verdict:** none — none were proposed.
**Packages flagged as suspicious [SUS]:** none.

> Note: Phase 1's SUMMARY records that a package-legitimacy tool was run destructively during that phase (`slopcheck install` rather than `scan`). No such tool was invoked in this research session, because **no new package is under consideration** — the audit reduces to "these two are already in the committed hash-pinned lock."

---

## Architecture Patterns

### Module layout

```
src/eacp/
├── __init__.py          # unchanged — version only, no re-exports (Phase 1 note)
├── backends.py          # unchanged — the single import chokepoint
├── errors.py            # += PolicyError, DuplicateEntrypointError, CapabilityError
├── capabilities.py      # NEW  Capability Literal + KNOWN_CAPABILITIES frozenset
├── policy.py            # NEW  _StrictLoader, load_policy_file, Policy, policy_hash
├── registry.py          # NEW  entrypoint allowlist, Workflow, register_workflow
├── store.py             # NEW  RunStore Protocol, RunRecord, SQLiteRunStore
└── adapters/*.py        # += CAPABILITIES constant (3 one-line edits)
```

### Data flow

```
 policy.yaml ──► _StrictLoader ──► dict ──► Policy.model_validate ──► Policy (frozen)
   (bytes)       dup-key reject      │        extra="forbid"              │
                 size cap            │        StrictInt / Decimal         │
                 mapping-root guard  │                                    ▼
                                     │                          policy_hash(p) ── sha256 hex
                                     │                                    │
 workflow.yaml ─► same loader ──► Workflow.model_validate                 │
                                     │                                    │
                                     ▼                                    │
                         register_workflow(wf, policy) ◄──────────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          ▼ (1)                      ▼ (2)                      ▼ (3)
   entrypoint in                backend_type in          load_backend_module(bt)
   _ENTRYPOINTS?                available_backends()      → mod.CAPABILITIES
   ValueError if not            ValueError if not         MissingExtraError if no extra
                                                                   │
                                                                   ▼
                                               policy.requires - CAPABILITIES == ∅ ?
                                               CapabilityError if not
                                                                   │
                                                                   ▼
                                                        _WORKFLOWS[wf.id] = wf
                                                                   │
  ── runtime (Phases 5/6/7) ────────────────────────────────────── ▼
        adapter ──► RunStore.start_run(RunRecord(..., policy_hash=...))
                ──► RunStore.append_step(...) × N
                ──► RunStore.finish_run(...)
```

**The ordering of gates (1)→(2)→(3) is load-bearing**, not cosmetic. `load_backend_module` is the only step that can raise `MissingExtraError`; putting it last means a typo'd entrypoint reports "unknown entrypoint" rather than "install `eacp[crewai]`". See §Pitfall 5.

### Pattern 1: pydantic at the boundary, dataclasses inside

`Policy` and `Workflow` parse untrusted YAML → pydantic. `RunRecord` and `StepRecord` are produced by our own adapter code → `@dataclass(frozen=True, slots=True)`. This keeps validation cost on the path that needs it and keeps the store's hot path (one `append_step` per node) allocation-cheap.

### Pattern 2: allowlist dict, exactly as `backends.py` does it

`_ENTRYPOINTS: dict[str, Callable[..., object]]` with `register_entrypoint` / `resolve_entrypoint`. `KeyError` → `ValueError` listing the registered names, `from None` to suppress chaining — identical to `load_backend_module`'s shape. Nothing in `registry.py` calls `importlib`.

### Pattern 3: one canonicalization function, used everywhere

```python
def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
```
Phase 4's audit log will want the same guarantee. Export it; do not let a second copy appear.

### Anti-patterns to avoid

- **`set[str]` for any hashed field.** Nondeterministic serialization order. Verified three times.
- **`yaml.load(text)` with the default `Loader`** — full constructor, executes `!!python/` tags. Only `SafeLoader` or a subclass of it.
- **f-string SQL.** Every value is a `?` parameter. Table names and `ORDER BY` direction are *not* parameterizable (both raise `OperationalError` if you try), so they must be literals in the SQL string — never caller input.
- **A `close()`-less long-lived module-global connection.** CrewAI executes on threads; the default `check_same_thread=True` raises `ProgrammingError` cross-thread (verified).
- **`:memory:` in tests.** With connection-per-call each `connect(":memory:")` is a *fresh empty database* — verified: the second connection reports `no such table`. Use `tmp_path`.
- **Putting approval or audit records in `RunStore`.** Phase 4 scope; they want their own Protocol.

---

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---------|-------------|-------------|-----|
| Canonical JSON | A custom recursive key-sorting serializer | `model.model_dump(mode="json")` then `json.dumps(sort_keys=True, separators=(",",":"))` | `mode="json"` already handles `Decimal`→str, `datetime`→ISO, `tuple`→list. Two stdlib calls. |
| Strict config parsing | A hand-written field checker | `ConfigDict(extra="forbid")` | Gives you the offending field name and `extra_forbidden` type for free, which §Specifics asks for. |
| Rejecting duplicate YAML keys | Regex pre-scan of the file | A `SafeLoader` subclass overriding the mapping constructor | ~12 lines, operates on the parsed node tree, immune to comments/quoting/nesting. |
| Schema migration | An `alembic` dependency | `PRAGMA user_version` + an if-ladder | The store has two tables and will change twice. Verified: `user_version` persists across connections. |
| Run-record dedup / ordering | An in-memory sequence counter | `PRIMARY KEY (run_id, seq)` | The DB already enforces it, and a duplicate `seq` becomes an `IntegrityError` instead of a silently-overwritten step. |
| Orphan-step prevention | A "does the run exist?" SELECT before each insert | `REFERENCES runs(run_id)` + `PRAGMA foreign_keys=ON` | Verified: `FOREIGN KEY constraint failed`. **Note `foreign_keys` is OFF by default and is per-connection** — it must be set in `_connect()`, not once at schema creation. |
| Protocol conformance checking | `@runtime_checkable` + `isinstance` asserts | `_: RunStore = SQLiteRunStore(path)` at module scope, checked by `mypy --strict` | See §Finding 7. |

**Key insight:** every hand-rolled option above is *bigger* than the stdlib one and worse on exactly the edge case this phase exists to close.

---

## Findings

### Finding 1 — Hash stability has two silent killers, and `model_dump_json()` is one of them

**HIGH — executed.**

`BaseModel.model_dump_json()` emits keys in **field-declaration order**, and neither it nor `pydantic_core.to_json` accepts a `sort_keys` argument:

```
model_dump_json params: ['self','indent','ensure_ascii','include','exclude','context',
  'by_alias','exclude_unset','exclude_defaults','exclude_none','exclude_computed_fields',
  'round_trip','warnings','fallback','serialize_as_any']
sort_keys present: False
```
[VERIFIED: `inspect.signature(BaseModel.model_dump_json)` in `.venv`, pydantic 2.12.5]

Consequence — two models with the same data but different field-declaration order hash differently:
```
declA: {"b":2,"a":1}   sha256 3fb75453…
declB: {"a":1,"b":2}   sha256 43258cff…
```
So a developer alphabetizing the `Policy` class body invalidates every stored policy hash. Sorting keys at serialization time removes the coupling entirely.

**The worse killer: `set[str]`.** Three consecutive runs of the identical program, `compliance_tags: set[str]`:
```
{"tags":["pci","iso27001","hipaa","soc2","gdpr"]}
{"tags":["pci","soc2","hipaa","iso27001","gdpr"]}
{"tags":["pci","hipaa","gdpr","iso27001","soc2"]}
```
[VERIFIED: 3× `PYTHONHASHSEED=random .venv/bin/python`]

`set[str]` is the *natural* type for `allowed_tools` / `compliance_tags` and it makes POLICY-04's success criterion ("stable for identical policy content") non-deterministically false. **Use `list[str]` with a validator that rejects duplicates and returns `sorted(v)`.** This also gives a better error than a set would (a duplicated tool name becomes a validation error instead of vanishing).

**Sub-question answered — unset optional vs explicit `None`:** they serialize **identically** by default.
```
unset:          {"zeta":1,"alpha":"a","mid":["b","c"],"opt":null}
explicit None:  {"zeta":1,"alpha":"a","mid":["b","c"],"opt":null}
identical: True
```
…**but only if you do not pass `exclude_unset=True`**, which does distinguish them:
```
exclude_unset, unset:         {"zeta":1,"alpha":"a","mid":["b","c"]}
exclude_unset, explicit None: {"zeta":1,"alpha":"a","mid":["b","c"],"opt":null}
```
[VERIFIED: executed]

**Rule for the planner: the hash path must never use `exclude_unset`, `exclude_defaults`, or `exclude_none`.** Under D-08 every field is required anyway, so the question is moot today — but D-08 is explicitly relaxable, and the day someone adds an optional field is the day this becomes a live hash-stability bug. Write it as a comment next to `policy_hash`.

**Sub-question answered — `policy_id` inside or outside the payload: OUTSIDE.** So is `version`. The reasoning, and it is not merely aesthetic:

- It is what content addressing means everywhere adjacent: a git blob hash excludes the filename, an OCI image digest excludes the tag, and OPA keeps a bundle's `revision` field separate from the policy content it labels [CITED: openpolicyagent.org/docs/management-bundles]. The OPSF policy-token spec frames it as "the hash of an immutable serialised policy representation," i.e. of the *representation*, not of the name [CITED: github.com/opsf-org/pct-spec/issues/79].
- It buys a governance property the project actually wants: with `policy_id` and `version` excluded, `hash(v1) == hash(v2)` answers "did the enforceable rules change?" in one comparison. With them included, every version bump changes the hash and the question is unanswerable.
- Nothing is lost, because POLICY-04 pins the hash *alongside* the id on every run record — the `runs` table carries both `policy_id` and `policy_hash`. Identity and content are both recorded; they are just recorded as two columns instead of one conflated one.

**The drift risk this creates, and its guard.** `exclude={"policy_id","version"}` means a *new* identity field added later is silently hashed unless someone remembers to exclude it. One assertion closes it:

```python
assert set(p.model_dump(mode="json")) - _IDENTITY_FIELDS == {
    "max_tokens_per_run", "max_cost_per_day", "allowed_tools", "forbidden_tools",
    "required_approval_nodes", "compliance_tags", "requires",
}, "hashed key set drifted"
```
[VERIFIED: passes in the end-to-end probe] — this is the one test that must exist for POLICY-04, more than the round-trip test.

**End-to-end proof.** Two YAML documents differing in key order, list order, `policy_id`, `version`, and `25.00` vs `25.0`:
```
hash A: 5a09c97db684d06b…
hash B: 5a09c97db684d06b…
STABLE: True
```
[VERIFIED: executed, §Code Example 2]

---

### Finding 2 — Model-level `strict=True` is wrong for this schema; use field-level `StrictInt`

**HIGH — executed.**

The appeal of `ConfigDict(strict=True)` is real: it blocks YAML's `yes`→`True`→`int 1` coercion, which in lax mode is accepted silently.

```
lax    int from True  -> 1                 # max_tokens_per_run: yes  =>  1 token
strict int from True  -> REJECT int_type
strict int from '10'  -> REJECT int_type
strict int from 10.0  -> REJECT int_type
```

But applied model-wide it breaks the money field, because YAML produces `int`/`float`, never `Decimal`:
```
strict Decimal from 100    -> REJECT is_instance_of
strict Decimal from '2.5'  -> REJECT is_instance_of
lax    Decimal from 100    -> {"cost":"100"}
lax    Decimal from True   -> REJECT decimal_type   # already safe without strict
```
[VERIFIED: executed]

So: **`StrictInt` on the integer fields, plain `Decimal` on the money field.** Lax `Decimal` already rejects booleans, which was the only reason to want strictness there. `StrictInt` blocks `True`, `"10"` and `10.0`; combine with `Field(ge=1)` so `max_tokens_per_run: 0` is rejected (`greater_than_equal`).

**`Decimal` canonicalization trap:** `Decimal("1.50")` and `Decimal("1.5")` are `==` but serialize to `"1.50"` and `"1.5"` — different hashes. `.normalize()` is not the fix (`Decimal("100").normalize()` → `1E+2`). A `quantize(Decimal("0.000001"))` field validator makes both `"1.500000"`. [VERIFIED: executed]

Also verified: pydantic converts a YAML float to `Decimal` via its string form, not its binary expansion — `Decimal(0.1)` in raw Python is `0.1000000000000000055511151231257827…`, but `Policy(max_cost_per_day=0.1)` serializes as `"0.100000"`. Good; no float-repr leakage into the hash.

---

### Finding 3 — `yaml.safe_load` has three silent failure modes; one is a governance bypass

**HIGH — executed, PyYAML 6.0.3.**

**(a) Duplicate keys are accepted, last one wins, no error.**
```python
yaml.safe_load("max_tokens_per_run: 100\nmax_tokens_per_run: 999999\n")
# -> {'max_tokens_per_run': 999999}
```
PyYAML collapses the duplicate during construction, so pydantic's `extra="forbid"` never sees it. In a file that governs spend limits, "append a line to override a limit, with no diff-visible schema violation" is a tampering primitive. **Mitigated by `_StrictLoader` (§Code Example 1), ~12 lines.** Registered as **T-02-01**.

**(b) YAML 1.1 scalar resolution mangles plausible values.**
```
{'a': False, 'b': True, 'c': True, 'd': False, 'e': False}   # no / yes / on / off / NO
{'v': '1.2.3', 't': 750, 'o': '0o777', 'n': 8, 'x': 1000}    # 12:30 -> 750 ! 010 -> 8 !
```
`12:30` becomes sexagesimal `750`; `010` becomes octal `8`; `1_000` becomes `1000`. For `max_tokens_per_run: 010` the author writes ten and gets eight, silently. `StrictInt` catches the *boolean* case (`yes` → `int_type` rejection) but **cannot** catch `010`→`8`, because 8 is a valid int. This is unfixable at the schema layer — mitigate by documenting it in the policy-YAML docs (Phase 10) and by the error message being precise when it does fire.

**(c) A non-mapping root produces a confusing pydantic error.**
```
''          -> None       '---\n'  -> None
'- a\n- b'  -> ['a','b']  'text'   -> 'text'
```
An empty policy file parses to `None`, and `Policy.model_validate(None)` reports a generic `model_type` error. **Guard with `isinstance(data, dict)`** and raise a message naming the actual type — verified output: `policy document must be a YAML mapping, got list`.

**(d) What `safe_load` does correctly:** `!!python/object/apply:os.system ['echo pwned']` raises `ConstructorError`. [VERIFIED] The RCE vector is genuinely closed by `SafeLoader`; the subclass in §Code Example 1 inherits that and only *adds* the duplicate-key check.

**(e) What `safe_load` does NOT protect against: alias amplification.**
```
source bytes: 220
expanded leaf count: 531,441   in 0.06s
```
[VERIFIED: 6-level nested anchor expansion under `yaml.safe_load`]

Six more levels is ~10^9 nodes. For v1 the policy file is locally authored, so severity is low — but a one-line `len(text.encode()) > 64_000` guard before parsing costs nothing and is the difference between "we thought about it" and "we didn't." Registered as **T-02-02**.

---

### Finding 4 — The capability vocabulary: two names, and the requirement must be explicit

**MEDIUM — reasoned from REQUIREMENTS.md + STATE.md; the framework-behaviour inputs are Phase 1 research and CLAUDE.md, not re-verified against installed frameworks (crewai is uninstallable on this host).**

**Should a policy express a capability requirement implicitly or explicitly? Explicitly.**

The implicit route — "non-empty `required_approval_nodes` implies an approval capability" — is dead on arrival, and the reason is worth stating precisely. APPROVAL-05 says CrewAI and ag2 provide **inline** approval and LangGraph provides **durable** (APPROVAL-04). All three therefore have *an* approval capability. An implicit "needs approval" requirement is satisfied by every backend, so WORKFLOW-03's gate could never fire, and its success criterion ("fails loudly at registration") would have no reachable test case. The axis on which the three genuinely differ is **durability**, and no combination of the six POLICY-02 fields expresses "this approval must survive a process exit." That is a deployment/compliance intent, not a limit — it has to be stated.

REQUIREMENTS.md itself already speaks this way: WORKFLOW-03's own example is *"a `durable_pause` requirement against an adapter that can't provide it."*

**Recommended shape:**

```python
# eacp/capabilities.py  — core, framework-free
Capability = Literal["durable_approval", "inline_approval"]
KNOWN_CAPABILITIES: frozenset[str] = frozenset({"durable_approval", "inline_approval"})
```
```yaml
# policy.yaml
requires: [durable_approval]     # or []  — see below
```
```python
# adapters/langgraph_adapter.py
CAPABILITIES: frozenset[Capability] = frozenset({"durable_approval", "inline_approval"})
# adapters/crewai_adapter.py  /  adapters/ag2_adapter.py
CAPABILITIES: frozenset[Capability] = frozenset({"inline_approval"})
```
```python
missing = set(policy.requires) - set(mod.CAPABILITIES)
if missing:
    raise CapabilityError(
        f"Workflow {wf.id!r} requires {sorted(missing)}, which backend "
        f"{wf.backend_type!r} does not provide. It provides: {sorted(mod.CAPABILITIES)}."
    )
```

**Why `frozenset[str]` and not an enum or a dict.** The gate is a set difference — one line. An `Enum` adds a name→value indirection for strings that are already the wire format (they appear verbatim in YAML). A `dict[str, bool]` makes "absent" and "declared False" two different things, which is a distinction nobody needs. The `Literal` alias is the type-safety layer: `mypy --strict` rejects a typo in an adapter's declaration, and pydantic rejects a typo in a policy's `requires` at load time (`literal_error`, verified).

**Why exactly two names, and the rule for adding a third.** I considered `tool_call_interception`, `pre_call_admission`, `delegation_tool_enforcement`, and `provider_token_usage`. All four are capabilities all three adapters are *expected* to have (per CREWAI-01 / AG2-02 / LANGGRAPH-01), which makes them gates that can never fire — dead code with a documentation cost. `delegation_tool_enforcement` is worse than dead: LangGraph has no agent-delegation concept, so it would report "lacks" for something that is *not applicable*, and the registry would reject a perfectly valid registration.

> **Rule to write into the module docstring:** *a capability name earns its place only when at least one shipped adapter genuinely lacks it.* Phases 5–7 will discover such cases (BUDGET-05's `usage_source` is the likeliest candidate); add them then, with the adapter that lacks it landing in the same commit.

`inline_approval` is kept despite all three having it, for two reasons: DOCS-02 requires an AdapterCapabilities matrix and a one-column matrix is not a matrix, and it makes the vocabulary self-describing rather than a single magic string.

**Should `requires` be a required field (D-08) or default to `[]`?** Recommend **required**, `requires: []` written explicitly. D-08's own rationale applies verbatim — a missing `requires` defaulting to "demand nothing" is the permissive direction, the same failure shape as a missing budget defaulting to infinity. The cost is eight characters per policy file; the benefit is that "this policy makes no durability demand" is an authored statement rather than an omission. Flagged as the one place the planner might reasonably disagree; it is a one-character change (`= []`) either way.

**Validate the adapter's own declaration too.** `mypy` catches a typo statically, but an adapter is only type-checked if it's in `files = ["src","tests"]` *and* its framework is installed (mypy will `ignore_missing_imports` otherwise). One runtime line in the registry closes it:
```python
unknown = set(mod.CAPABILITIES) - KNOWN_CAPABILITIES
if unknown:
    raise CapabilityError(f"Adapter {wf.backend_type!r} declares unknown capabilities: {sorted(unknown)}")
```

**The honesty gap (registered as T-02-12, deferred to Phase 7):** nothing in Phase 2 verifies that an adapter declaring `durable_approval` actually delivers it. CONFORM-01's parametrized suite is the right place for that assertion, and it should be written as "for each adapter, `durable_approval ∈ CAPABILITIES` ⟺ a run survives process exit." Note it in the Phase 7 plan now, while the reasoning is fresh.

---

### Finding 5 — The entrypoint is an allowlist *key*, not a path, and this is forced by WORKFLOW-01

**HIGH — executed.**

WORKFLOW-01 calls `entrypoint` "an opaque pointer to user-authored code." Three candidate value shapes:

| Shape | Example | Verdict |
|-------|---------|---------|
| Dotted import path | `myapp.flows:build_graph` | **Rejected.** Resolving it means `importlib.import_module(<caller string>)`, which is the exact pattern Phase 1's T-01-04b exists to prevent, and it makes the pointer *transparent* (it encodes module structure) rather than opaque. |
| Direct callable at registration | `register_workflow(wf, fn=build_graph)` | **Rejected.** Then a workflow YAML can't name its own entrypoint, and WORKFLOW-01 lists `entrypoint` as a schema field. |
| **Registered name** | `entrypoint: contract_review` | **Recommended.** The app author calls `register_entrypoint("contract_review", build_graph)` in Python; the YAML carries only a dict key. Genuinely opaque, and the string never reaches an import. |

The registered-name design is D-10 exactly, and it mirrors `_BACKENDS` line for line: allowlist lookup → `ValueError` listing the known keys → resolve only allowlisted values. **`registry.py` should contain zero `importlib` calls**, which makes it AST-assertable the same way `01-SECURITY.md` asserted `backends.py` has exactly one `import_module` site.

Two additions beyond D-10, both one-liners, both verified:

1. **Charset constraint on the name.** `^[a-z0-9][a-z0-9_-]{0,63}$`. Entrypoint names surface in error messages, run records, and (Phase 4) CLI output; a conservative charset means they are never a log-injection or path-traversal shaped string. Verified: `os.system` and `../etc` both rejected by the pattern before the dict is ever touched.
2. **Re-registration raises.** A second `register_entrypoint("contract_review", other_fn)` must raise, not overwrite. Silently swapping what a registered name points to is a hijack primitive in any process that imports third-party workflow modules. Verified: `DuplicateEntrypointError: Entrypoint 'contract_review' is already registered`. Registered as **T-02-05**.

**`backend_type` single-sourcing.** `Literal["langgraph","crewai","ag2"]` gives mypy narrowing and a pydantic error that names the allowed values, but it duplicates `_BACKENDS`. Do not replace it with a runtime validator against `available_backends()` (you lose static narrowing); instead keep the `Literal` and add the drift test:
```python
assert set(typing.get_args(BackendType)) == set(available_backends())
```
Two lines, zero runtime cost, impossible to drift.

---

### Finding 6 — `RunStore`: six methods, caller-generated `run_id`, connection-per-call

**HIGH — executed end to end.**

**Surface.** Append-mostly means write-once rows plus a few filtered reads. Six methods cover TRACE-03 with nothing spare:

```python
class RunStore(Protocol):
    def start_run(self, run: RunRecord) -> None: ...
    def finish_run(self, run_id: str, *, status: RunStatus, ended_at: str,
                   metrics: Mapping[str, object]) -> None: ...
    def append_step(self, run_id: str, *, seq: int, name: str, started_at: str,
                    ended_at: str, outcome: str, attributes: Mapping[str, object]) -> None: ...
    def get_run(self, run_id: str) -> RunRecord | None: ...
    def list_runs(self, *, workflow_id: str | None = None, since: str | None = None,
                  limit: int = 100) -> Sequence[RunRecord]: ...
    def list_steps(self, run_id: str) -> Sequence[StepRecord]: ...
```

`start_run` + `finish_run` rather than one `write_run` because a run is *not* complete when it starts — APPROVAL-02 requires `eacp approve <run_id>` to find a row for a run that is still paused, from a different process. A single terminal write would make paused runs invisible.

**Who generates `run_id`: the caller.** Three independent reasons, all from downstream requirements:
- LANGGRAPH-02 pins `thread_id = run_id` on the SQLite checkpointer — the id must exist *before* the graph is compiled and therefore before the store is touched.
- CREWAI-03 requires run identity propagated across CrewAI's threads; that propagation starts at the adapter, not at the store.
- If the store minted ids, a store outage would block run *start*. With caller-minted ids the run can execute and the history write is the only thing that fails.

Use `uuid.uuid4().hex`. **Not `uuid7`** — verified absent on 3.12 and excluded by `requires-python < 3.14`. Sortability comes from the `started_at` column and `idx_runs_workflow_started`, not from the id.

**Transaction boundaries: one per method. Do not batch.** A crash mid-run should leave the `runs` row at `status='running'` with the steps written so far — that is the forensically useful state, and it is what per-method commits give you for free. Batching steps into the run's transaction would discard exactly the evidence you want after a crash.

**`@runtime_checkable`: no.** See §Finding 7.

**Connection-per-call vs long-lived — measured.**
```
connect-per-write : 1192 µs/op
long-lived conn   :  161 µs/op
bare connect+close:   66 µs
```
[VERIFIED: 2000 inserts each, WAL, this machine]

~1 ms extra per run-history row. An agent run writing 50 steps pays ~60 ms total against LLM calls measured in seconds. In exchange, connection-per-call deletes:
- **thread affinity** — verified: a shared connection used from another thread raises `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`. CrewAI executes on threads (CREWAI-03).
- **connection lifecycle** — no `close()` on the Protocol, no context manager, no "who owns the handle" question.
- **cross-process coherence** — Phase 4's `eacp approve` runs in a second process and just works.

Take it. Mark the ceiling in a comment so the upgrade path is visible:
```python
# ponytail: one connection per call — ~1 ms/write, deletes all thread-affinity
# concerns. If run-history writes ever dominate a profile, switch to a
# thread-local connection; the Protocol does not change.
```

**Schema (verified working, with `PRAGMA foreign_keys=ON` enforcing the FK):**

```sql
CREATE TABLE IF NOT EXISTS runs (
  run_id       TEXT PRIMARY KEY,
  workflow_id  TEXT NOT NULL,
  backend_type TEXT NOT NULL,
  policy_id    TEXT NOT NULL,
  policy_hash  TEXT NOT NULL,          -- POLICY-04
  status       TEXT NOT NULL,
  started_at   TEXT NOT NULL,          -- ISO-8601 UTC, see Pitfall 1
  ended_at     TEXT,
  metrics      TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_runs_workflow_started ON runs(workflow_id, started_at);

CREATE TABLE IF NOT EXISTS run_steps (
  run_id     TEXT NOT NULL REFERENCES runs(run_id),
  seq        INTEGER NOT NULL,
  name       TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at   TEXT NOT NULL,
  outcome    TEXT NOT NULL,
  attributes TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (run_id, seq)
);
```

`attributes` is a free-form JSON blob deliberately — TRACE-02 (Phase 5) wants OpenTelemetry `gen_ai.*` attribute names, and a free-form column means Phase 5 needs no migration and **Phase 2 imports no OTel**. Verified round-trip with `{"gen_ai.usage.input_tokens": 100}`.

**Migrations: `PRAGMA user_version`.** Verified to persist across connections. Set `user_version=1` at creation; when the schema changes, an `if current < 2: ...` ladder in `_connect`-time bootstrap is the whole mechanism. No alembic.

---

### Finding 7 — `@runtime_checkable` would be actively misleading here

**HIGH — executed.**

```python
@runtime_checkable
class RunStore(Protocol):
    def start_run(self, run_id: str, workflow_id: str) -> None: ...
    def get_run(self, run_id: str) -> str | None: ...

class Wrong:
    def start_run(self, a: int, b: int, c: int, d: int) -> int: return 0
    def get_run(self) -> None: return None
```
```
isinstance(Wrong(), RunStore) -> True     <-- signature-blind
isinstance(Missing(), RunStore) -> False  <-- only method NAMES are checked
```
```
mypy --strict: error: Incompatible types in assignment
  (expression has type "Wrong", variable has type "RunStore")  [assignment]
  note: Following member(s) of "Wrong" have conflicts: ...
```
[VERIFIED: both executed]

A runtime `isinstance` check against this Protocol would pass a store whose every method has the wrong arity — the exact failure a "pluggable interface" is supposed to prevent — while giving a reviewer the impression it was verified. **Skip the decorator.** Put a static probe at the bottom of `store.py`:

```python
_conformance: RunStore = SQLiteRunStore  # type: ignore[assignment]  # class-level probe
```
or, cleaner, in the test module:
```python
def test_sqlite_store_satisfies_protocol(tmp_path: Path) -> None:
    store: RunStore = SQLiteRunStore(tmp_path / "runs.db")   # mypy --strict enforces
    assert store.get_run("nope") is None
```
The annotation is what mypy checks; the assert is what pytest checks. One function, both guarantees.

---

## Common Pitfalls

### Pitfall 1: the default `datetime` adapter is deprecated on Python 3.12
**What goes wrong:** `cur.execute("insert into t values(?)", (datetime.now(UTC),))` emits
`DeprecationWarning: The default datetime adapter is deprecated as of Python 3.12`.
[VERIFIED: raised as an error under `warnings.simplefilter("error", DeprecationWarning)` on 3.12.13]
**Why:** CPython removed the implicit datetime↔TEXT adapters' blessing; they will be removed outright.
**How to avoid:** store `datetime.now(datetime.UTC).isoformat(timespec="microseconds")` as TEXT. This is also what you want independently — ISO-8601 UTC strings sort lexicographically, which is what `ORDER BY started_at` and the `since=` filter rely on. Never store a naive datetime; never store an epoch float.
**Warning sign:** any `DeprecationWarning` from `sqlite3` in the test output. Add `filterwarnings = ["error::DeprecationWarning"]` to `[tool.pytest.ini_options]` so this can never sneak in.

### Pitfall 2: `PRAGMA journal_mode=WAL` fails inside a transaction
**What goes wrong:** `sqlite3.OperationalError: cannot change into wal mode from within a transaction` [VERIFIED].
**Why:** with the legacy `isolation_level=''` default, the first DML statement opens an implicit transaction that is still open when you get around to the pragma.
**How to avoid:** set WAL as the **first statement after connect, before any DML**, at store creation. It persists in the database file header — a later `connect()` reports `('wal',)` without re-setting it [VERIFIED] — so it belongs in `__init__`, not in `_connect`.
**Related:** WAL creates **three** files (`runs.db`, `runs.db-wal`, `runs.db-shm`) [VERIFIED]. Whatever `.gitignore` pattern the phase adds must cover all three, and any doc telling a user to "copy the store file" is wrong.

### Pitfall 3: `PRAGMA foreign_keys` is OFF by default and is per-connection
**What goes wrong:** orphan `run_steps` rows for a `run_id` that was never inserted; the `REFERENCES` clause is inert.
**Why:** SQLite defaults `foreign_keys` to `0` for backwards compatibility [VERIFIED: `pragma foreign_keys` → `(0,)` on a fresh connection], and the setting does **not** persist in the file the way `journal_mode` does.
**How to avoid:** `c.execute("PRAGMA foreign_keys=ON")` inside `_connect()`, on every connection. With connection-per-call that is exactly one place. Verified working: `append_step` against an unknown run raises `IntegrityError: FOREIGN KEY constraint failed`.

### Pitfall 4: `:memory:` silently breaks under connection-per-call
**What goes wrong:** the store's `__init__` creates the tables, then every subsequent method reports `no such table: runs`.
**Why:** each `sqlite3.connect(":memory:")` creates an independent, empty database. [VERIFIED]
**How to avoid:** tests use `tmp_path / "runs.db"`. If an in-memory store is ever genuinely wanted, it needs `file::memory:?cache=shared` with `uri=True` and a held connection — which is a different design; don't. Also note `PRAGMA journal_mode=WAL` on `:memory:` silently returns `('memory',)` rather than erroring, so a `:memory:` store would also not be in WAL.
**Warning sign:** a test that passes when run alone and fails when the store is reused.

### Pitfall 5: gate ordering turns a typo into the wrong error
**What goes wrong:** `register_workflow` with a misspelled `entrypoint` reports `MissingExtraError: install eacp[crewai]`.
**Why:** whichever gate runs first wins, and `load_backend_module` is the only one that can raise about installation.
**How to avoid:** entrypoint → `backend_type` → `load_backend_module`/capabilities, in that order. The first two are pure dict lookups with no import; only the third touches the filesystem. This also means the common case (bad name) is the cheapest check.

### Pitfall 6: table names and ORDER BY direction cannot be parameterized
**What goes wrong:** a developer reaches for `f"SELECT * FROM {table}"` after discovering `execute("select * from ?", ("runs",))` raises `OperationalError` [VERIFIED — as does `order by ts ?` with `("desc",)`].
**How to avoid:** the store has two tables and one sort direction, all known at authoring time. Write them as literals. Every *value* is a `?`. Verified: `list_runs(workflow_id="x'; DROP TABLE runs;--")` returns `[]` and the table survives.

### Pitfall 7: `ValidationError` echoes the offending input value
**What goes wrong:** `e.errors()` entries include an `'input'` key carrying the rejected value verbatim (`{'type':'extra_forbidden','loc':('bogus',),'input':3}`) [VERIFIED]. If a policy file ever carries anything sensitive, it lands in whatever logs the error.
**Why it is low-severity here:** POLICY-02's fields are limits, tool names and compliance tags — no secrets by design.
**How to avoid:** keep it that way. If a credential-shaped field is ever proposed for the policy schema, it must not be — policies reference tools by name, they do not carry keys. Use `e.errors(include_url=False)` to keep messages compact.
**Scope clarification vs T-01-05:** Phase 1's rule was that a *library ImportError* must not disclose venv/env/filesystem locations. A policy loader naming **the user's own policy file** in its error is desirable, not a violation. Phase 2 may include the policy path in `PolicyError`; it must not include `sys.prefix`, `sys.executable`, `sys.path` or environment values.

---

## Code Examples

All four blocks below were executed in this repo's `.venv` today with the outputs shown. They are copy-paste starting points, not sketches.

### Code Example 1 — duplicate-key-rejecting safe loader + mapping guard

```python
# eacp/policy.py
from typing import Any
import yaml

MAX_POLICY_BYTES = 64 * 1024   # T-02-02: bounds YAML alias amplification


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that additionally refuses duplicate mapping keys."""


def _no_duplicate_keys(
    loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r}", key_node.start_mark
            )
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
)


def load_yaml_mapping(text: str) -> dict[str, Any]:
    if len(text.encode("utf-8")) > MAX_POLICY_BYTES:
        raise ValueError(f"document exceeds {MAX_POLICY_BYTES} bytes")
    data = yaml.load(text, Loader=_StrictLoader)   # SafeLoader subclass, not yaml.load default
    if not isinstance(data, dict):
        raise ValueError(f"document must be a YAML mapping, got {type(data).__name__}")
    return data
```

Verified rejections:
```
rejected [duplicate key]:      duplicate key 'max_tokens_per_run'
rejected [non-mapping root]:   document must be a YAML mapping, got list
rejected [python tag]:         ConstructorError          (inherited from SafeLoader)
```

### Code Example 2 — strict policy schema + canonical content hash

```python
# eacp/policy.py (continued)
import hashlib, json
from decimal import Decimal
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from eacp.capabilities import Capability

_COST_EXP = Decimal("0.000001")
_IDENTITY_FIELDS = frozenset({"policy_id", "version"})


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)   # D-08 + hashable

    policy_id: str
    version: StrictInt
    max_tokens_per_run: Annotated[StrictInt, Field(ge=1)]
    max_cost_per_day: Annotated[Decimal, Field(ge=0)]
    allowed_tools: list[str]
    forbidden_tools: list[str]
    required_approval_nodes: list[str]
    compliance_tags: list[str]
    requires: list[Capability]

    @field_validator("max_cost_per_day")
    @classmethod
    def _quantize(cls, v: Decimal) -> Decimal:
        # Decimal("1.50") and Decimal("1.5") are == but serialize differently.
        return v.quantize(_COST_EXP)

    @field_validator(
        "allowed_tools", "forbidden_tools", "required_approval_nodes",
        "compliance_tags", "requires",
    )
    @classmethod
    def _sorted_unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("duplicate entries are not allowed")
        return sorted(v)   # list order must not affect the content hash


def policy_hash(policy: Policy) -> str:
    """SHA-256 of the policy's enforceable content.

    policy_id and version are IDENTITY, not content: this hash answers
    "did the rules change?", which a version bump must not perturb.

    NEVER add exclude_unset/exclude_defaults/exclude_none here — they make an
    absent optional field hash differently from an explicit null.
    """
    payload = policy.model_dump(mode="json", exclude=set(_IDENTITY_FIELDS))
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

Verified with two YAML files differing in key order, list order, `policy_id`, `version`, and `25.00` vs `25.0`:
```
hash A: 5a09c97db684d06b…
hash B: 5a09c97db684d06b…
STABLE: True
hashed key set pinned OK
```
Verified rejections:
```
rejected [missing required fields]: ('version',)            missing
rejected [unknown field]:           ('bogus_field',)        extra_forbidden
rejected [yaml bool as int]:        ('max_tokens_per_run',) int_type
rejected [unknown capability]:      ('requires', 0)         literal_error
```

### Code Example 3 — entrypoint allowlist (mirrors `backends.py`)

```python
# eacp/registry.py
import re
from collections.abc import Callable

from eacp.errors import DuplicateEntrypointError

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_ENTRYPOINTS: dict[str, Callable[..., object]] = {}


def register_entrypoint(name: str, fn: Callable[..., object]) -> None:
    """Add a workflow entrypoint to the allowlist. Re-registration is refused."""
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"Invalid entrypoint name {name!r}: must match {_NAME_RE.pattern}")
    if name in _ENTRYPOINTS:
        raise DuplicateEntrypointError(f"Entrypoint {name!r} is already registered")
    _ENTRYPOINTS[name] = fn


def resolve_entrypoint(name: str) -> Callable[..., object]:
    # Allowlist lookup only. This module contains no importlib call: a
    # caller-supplied string can never become an import target (T-02-04).
    try:
        return _ENTRYPOINTS[name]
    except KeyError:
        raise ValueError(
            f"Unknown entrypoint {name!r}. Registered: {sorted(_ENTRYPOINTS)}"
        ) from None
```

Verified:
```
resolve ok: graph
entrypoint rejected: Invalid entrypoint name 'os.system': must match ^[a-z0-9][a-z0-9_-]{0,63}$
entrypoint rejected: Invalid entrypoint name '../etc': must match ^[a-z0-9][a-z0-9_-]{0,63}$
entrypoint rejected: Entrypoint 'contract_review' is already registered
resolve   rejected: Unknown entrypoint 'nope'. Registered: ['contract_review']
```

### Code Example 4 — `SQLiteRunStore` core

```python
# eacp/store.py
import json, sqlite3
from contextlib import closing
from pathlib import Path


class SQLiteRunStore:
    """Run-history store. One connection per call — see the ponytail note below."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        with closing(self._connect()) as c:
            c.execute("PRAGMA journal_mode=WAL")   # first, before any DML (Pitfall 2)
            c.executescript(_SCHEMA)
            c.execute("PRAGMA user_version=1")

    # ponytail: one connection per call — measured ~1 ms/write vs 161 µs for a
    # long-lived handle. Buys thread-safety and cross-process coherence for free.
    # Upgrade path if writes ever dominate a profile: a thread-local connection.
    # The Protocol does not change.
    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._path, timeout=30.0)
        c.execute("PRAGMA foreign_keys=ON")   # per-connection, OFF by default (Pitfall 3)
        c.row_factory = sqlite3.Row
        return c

    def start_run(self, run: RunRecord) -> None:
        with closing(self._connect()) as c, c:       # `with c` = commit/rollback
            c.execute(
                "INSERT INTO runs (run_id,workflow_id,backend_type,policy_id,"
                "policy_hash,status,started_at,ended_at,metrics) VALUES (?,?,?,?,?,?,?,?,?)",
                (run.run_id, run.workflow_id, run.backend_type, run.policy_id,
                 run.policy_hash, run.status, run.started_at, run.ended_at,
                 json.dumps(run.metrics, sort_keys=True)),
            )

    def finish_run(self, run_id: str, *, status: RunStatus, ended_at: str,
                   metrics: Mapping[str, object]) -> None:
        with closing(self._connect()) as c, c:
            cur = c.execute(
                "UPDATE runs SET status=?, ended_at=?, metrics=? WHERE run_id=?",
                (status, ended_at, json.dumps(metrics, sort_keys=True), run_id),
            )
            if cur.rowcount == 0:                    # silent no-op is worse than a raise
                raise KeyError(f"unknown run_id {run_id!r}")

    def list_runs(self, *, workflow_id: str | None = None, since: str | None = None,
                  limit: int = 100) -> Sequence[RunRecord]:
        sql = ["SELECT * FROM runs WHERE 1=1"]
        args: list[object] = []
        if workflow_id is not None:
            sql.append("AND workflow_id=?"); args.append(workflow_id)
        if since is not None:
            sql.append("AND started_at>=?"); args.append(since)
        sql.append("ORDER BY started_at DESC LIMIT ?")
        args.append(min(max(limit, 1), 1000))        # T-02-10: clamp, never trust the caller
        with closing(self._connect()) as c:
            return [_row_to_run(r) for r in c.execute(" ".join(sql), args)]
```

Verified end to end:
```
get_run:            RunRecord(d401daf0, succeeded, {'cost': '0.02', 'tokens': 300})
list_runs(filter):  [RunRecord(d401daf0, succeeded, …)]
list_runs(miss):    []
steps:              3   {"gen_ai.usage.input_tokens": 0}
unknown run_id ->   "unknown run_id 'nope'"
FK enforced ->      FOREIGN KEY constraint failed
injection attempt:  []        (table still there: 1 row)
cross-thread read:  [True]
```

---

## State of the Art

| Old approach | Current approach | When changed | Impact on this phase |
|--------------|------------------|--------------|----------------------|
| `sqlite3` implicit `datetime` adapter | Store ISO-8601 TEXT explicitly | **Python 3.12** (deprecated; removal pending) | Direct — §Pitfall 1. Training data predating 3.12 will produce a deprecation warning. |
| `Connection.isolation_level` | `Connection.autocommit` (`sqlite3.LEGACY_TRANSACTION_CONTROL`) | **Python 3.12** | Verified present (`hasattr(c,"autocommit") is True`, default `-1`). Not needed here — `with closing(conn) as c, c:` works under the legacy default — but do not be surprised by it. |
| pydantic v1 `class Config: extra = "forbid"` | `model_config = ConfigDict(extra="forbid")` | pydantic 2.0 | Direct. v1 idioms in training data will not run. |
| `@validator` | `@field_validator` + `@classmethod` | pydantic 2.0 | Direct — both validators in §Code Example 2. |
| `gen_ai.usage.prompt_tokens` / `completion_tokens` | `gen_ai.usage.input_tokens` / `output_tokens` | OTel GenAI semconv (both still exported; the `prompt`/`completion` pair is the deprecated pair) | Phase 5, not Phase 2 — but it is why the `attributes` column is a free-form JSON blob. [VERIFIED: `opentelemetry-semantic-conventions 0.66b0` in this venv exports both] |
| `from opentelemetry.semconv.attributes import gen_ai_attributes` | `from opentelemetry.semconv._incubating.attributes import gen_ai_attributes` | semconv (GenAI is still incubating) | Phase 5. Verified: the stable `attributes` package contains **no** `gen_ai_attributes` module. Training data suggesting the stable path is wrong. |
| `uuid.uuid7()` for sortable ids | `uuid.uuid4()` + a timestamp column | `uuid7` lands in **Python 3.14** | Direct. `requires-python = "<3.14"` excludes it; verified absent on 3.12. |

**Deprecated / do not use in this phase:**
- `yaml.load(text)` without an explicit `Loader=` — full constructor.
- `@runtime_checkable` for interface verification — §Finding 7.
- `pydantic.parse_obj_as` / `BaseModel.parse_obj` — v1 API.
- Model-level `ConfigDict(strict=True)` on a schema with a `Decimal` field — §Finding 2.

---

## Runtime State Inventory

**Not applicable — this is a greenfield phase.** It creates four new modules and adds one constant to three existing placeholder files. It renames nothing, migrates nothing, and touches no stored data, service configuration, OS registration, secret, or build artifact.

The one forward-looking note: **this phase creates the first persistent on-disk artifact the project has** (`runs.db` + `runs.db-wal` + `runs.db-shm`). Add all three to `.gitignore` in the same task that creates the store, and decide the default path deliberately rather than by accident — `sqlite3.connect()` on a path whose parent directory does not exist fails with `OperationalError: unable to open database file` [VERIFIED], so `SQLiteRunStore.__init__` should `mkdir(parents=True, exist_ok=True)` the parent or document that the caller must.

---

## Environment Availability

Phase 2 depends on no external tool or service beyond the Python runtime already in use.

| Dependency | Required by | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| CPython | everything | ✓ | 3.12.13 (`.venv`) | — |
| `sqlite3` stdlib module | TRACE-03 | ✓ | module 2.6.0 / lib **3.53.2**, `threadsafety 3` | — |
| `pydantic` | POLICY-01/02, WORKFLOW-01 | ✓ | 2.12.5 | — |
| `PyYAML` | POLICY-01 | ✓ | 6.0.3 | — |
| `pytest` / `mypy` / `ruff` | validation | ✓ | 9.1.1 / 2.3.1 / 0.16.9 (`dev` group) | — |
| `uv` | lock/sync | ✓ | 0.12.19 (matches CI `UV_VERSION`) | — |
| langgraph / crewai / ag2 | **nothing in this phase** | n/a | — | — |

**Missing dependencies with no fallback:** none.
**Note for the planner:** the well-known Intel-Mac / `lancedb` blocker does **not** affect this phase. Every Phase 2 module and test runs with zero extras installed — which is also exactly how CI's `core` job runs them.

---

## Validation Architecture

### Test framework

| Property | Value |
|----------|-------|
| Framework | `pytest` **9.1.1** (+ `pytest-asyncio` 1.4.0, unused this phase) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths=["tests"]`, `asyncio_mode="auto"`, `--strict-markers` |
| Quick run command | `uv run --no-sync pytest -q tests/test_policy.py tests/test_registry.py tests/test_store.py` |
| Full suite command | `uv run pytest -q && uv run mypy --strict && uv run ruff check` |
| Existing coverage | `tests/test_packaging.py` (Phase 1) — do not modify |

### Phase requirements → test map

| Req | Behavior | Type | Automated command | File |
|-----|----------|------|-------------------|------|
| POLICY-01 | Unknown field rejected at load | unit | `pytest tests/test_policy.py::test_unknown_field_rejected -x` | ❌ Wave 0 |
| POLICY-01 | Non-mapping root / empty file rejected | unit | `…::test_non_mapping_root_rejected` | ❌ Wave 0 |
| POLICY-01 | **Duplicate key rejected** (T-02-01) | unit | `…::test_duplicate_key_rejected` | ❌ Wave 0 |
| POLICY-01 | `!!python/` tag rejected | unit | `…::test_python_tag_rejected` | ❌ Wave 0 |
| POLICY-01 | Oversized document rejected (T-02-02) | unit | `…::test_oversized_document_rejected` | ❌ Wave 0 |
| POLICY-02 | All six limit fields required, no defaults | unit | `…::test_every_limit_field_is_required` (parametrized over field names) | ❌ Wave 0 |
| POLICY-02 | YAML `yes` rejected for an int field | unit | `…::test_yaml_bool_rejected_for_int_limit` | ❌ Wave 0 |
| POLICY-04 | **Hash stable across key order, list order, id, version, `25.00`/`25.0`** | unit | `…::test_hash_is_content_addressed` | ❌ Wave 0 |
| POLICY-04 | Changing any limit changes the hash | unit | `…::test_hash_changes_when_a_limit_changes` (parametrized) | ❌ Wave 0 |
| POLICY-04 | **Hashed key set is pinned** (drift guard) | unit | `…::test_hashed_key_set_is_pinned` | ❌ Wave 0 |
| WORKFLOW-01 | Schema rejects `nodes`/`agents`/`edges` | unit | `pytest tests/test_registry.py::test_topology_fields_rejected` | ❌ Wave 0 |
| WORKFLOW-01 | `BackendType` Literal == `available_backends()` | unit | `…::test_backend_literal_matches_backends_module` | ❌ Wave 0 |
| WORKFLOW-02 | Unknown entrypoint rejected at **registration** | unit | `…::test_unregistered_entrypoint_rejected` | ❌ Wave 0 |
| WORKFLOW-02 | Malformed name rejected by charset | unit | `…::test_entrypoint_name_charset` (parametrized: `os.system`, `../etc`, `A`, `""`) | ❌ Wave 0 |
| WORKFLOW-02 | Re-registration raises (T-02-05) | unit | `…::test_duplicate_entrypoint_registration_rejected` | ❌ Wave 0 |
| WORKFLOW-02 | `registry.py` contains **zero** `importlib` calls (T-02-04) | unit (AST) | `…::test_registry_has_no_import_machinery` | ❌ Wave 0 |
| WORKFLOW-03 | Capability shortfall raises `CapabilityError` | unit | `…::test_capability_shortfall_rejected` (fake module via monkeypatch — no extra needed) | ❌ Wave 0 |
| WORKFLOW-03 | Unknown capability in `requires:` rejected at load | unit | `tests/test_policy.py::test_unknown_capability_rejected` | ❌ Wave 0 |
| TRACE-03 | Write run → steps → finish → read back | integration | `pytest tests/test_store.py::test_run_roundtrip -x` | ❌ Wave 0 |
| TRACE-03 | `list_runs` filters by workflow and `since` | integration | `…::test_list_runs_filters` | ❌ Wave 0 |
| TRACE-03 | `SQLiteRunStore` satisfies `RunStore` | static | `mypy --strict` on `tests/test_store.py` | ❌ Wave 0 |
| TRACE-03 | Cross-thread call succeeds | integration | `…::test_store_is_thread_safe` | ❌ Wave 0 |
| TRACE-03 | Orphan step rejected (FK on) | integration | `…::test_orphan_step_rejected` | ❌ Wave 0 |
| TRACE-03 | Value with SQL metacharacters is inert | integration | `…::test_filter_value_is_parameterized` | ❌ Wave 0 |
| Success criterion 4 | Zero framework code imported | unit | already covered by CI `core` job + `tests/test_packaging.py` | ✅ exists |

### Sampling rate
- **Per task commit:** `uv run --no-sync pytest -q <the task's test file>` + `uv run --no-sync mypy --strict`
- **Per wave merge:** `uv run pytest -q && uv run mypy --strict && uv run ruff check`
- **Phase gate:** full suite green, then `/gsd-verify-work`

### Wave 0 gaps
- [ ] `tests/test_policy.py` — POLICY-01, POLICY-02, POLICY-04
- [ ] `tests/test_registry.py` — WORKFLOW-01, -02, -03
- [ ] `tests/test_store.py` — TRACE-03
- [ ] `tests/conftest.py` — one `policy_yaml` fixture and one `store` fixture on `tmp_path` (**not** `:memory:` — §Pitfall 4)
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` += `filterwarnings = ["error::DeprecationWarning"]` — this is what makes §Pitfall 1 impossible to reintroduce
- No framework install needed. No CI change needed.

---

## Security Domain

`security_enforcement: true`, `security_asvs_level: 1`, `security_block_on: high`.

### Applicable ASVS categories

| ASVS category | Applies | Standard control in this phase |
|---------------|---------|--------------------------------|
| V2 Authentication | no | No identity surface in this phase. |
| V3 Session Management | no | No sessions. |
| V4 Access Control | **partial** | The entrypoint allowlist and the capability gate are authorization decisions over *what code may be registered*. Deny-by-default, allowlist-not-denylist. |
| V5 Input Validation | **yes** | The whole phase. `SafeLoader` subclass, `extra="forbid"`, `StrictInt`, `Literal`, charset-constrained names, byte cap, clamped `limit`. |
| V5.3 Output Encoding / Injection | **yes** | Parameterized SQL only; no f-string SQL; no dynamic identifiers. |
| V6 Cryptography | **partial** | SHA-256 via `hashlib` for content addressing only — **not** a signature or a MAC, and it must not be described as one. Nothing hand-rolled. |
| V7 Error Handling & Logging | **yes** | Error text names the offending field and the allowed values; no `sys.path`/`sys.prefix`/env values (T-01-05 continuity, with the scope clarification in §Pitfall 7). |
| V12 Files & Resources | **partial** | Policy-file byte cap; SQLite file permissions (T-02-11). |

### Threat register (Phase 2)

> **Process note carried from Phase 1:** these IDs are allocated from a **single phase-wide sequence**. Phase 1 numbered per-plan and collided `T-01-03`/`T-01-04` across two different threats each. Whichever plan a threat lands in, its ID keeps the number below.

| ID | STRIDE | Component | Threat | Proposed disposition |
|----|--------|-----------|--------|----------------------|
| **T-02-01** | Tampering | `policy.py` loader | Duplicate YAML key silently overrides a limit; `extra="forbid"` cannot see it because PyYAML collapses it first. **Demonstrated: `max_tokens_per_run` 100 → 999999, no error.** | mitigate — `_StrictLoader` rejects duplicates; `test_duplicate_key_rejected` |
| **T-02-02** | Denial of Service | `policy.py` loader | YAML alias amplification. **Demonstrated: 220 bytes → 531,441 nodes in 0.06 s under `safe_load`.** | mitigate — `MAX_POLICY_BYTES` check before parse; `test_oversized_document_rejected` |
| **T-02-03** | EoP / RCE | `policy.py` loader | `yaml.load` with the default `Loader` executes `!!python/object/apply` tags | mitigate — only `_StrictLoader` (a `SafeLoader` subclass) is ever used; grep gate asserting no bare `yaml.load(` / `yaml.unsafe_load` / `Loader=yaml.Loader` in `src/` |
| **T-02-04** | EoP | `registry.py` | A caller-supplied `entrypoint` string reaching an import target | mitigate — dict lookup only; **AST test asserting zero `importlib` references in `registry.py`**, mirroring `01-SECURITY.md`'s T-01-04b evidence |
| **T-02-05** | Tampering | `register_entrypoint` | Silent re-registration swaps what a registered name executes | mitigate — `DuplicateEntrypointError`; `test_duplicate_entrypoint_registration_rejected` |
| **T-02-06** | Tampering | `store.py` | SQL injection through `workflow_id` / `since` / `run_id` | mitigate — `?` parameters only; grep gate for f-string/`%`/`.format` inside any `execute(`; `test_filter_value_is_parameterized` (verified: `"x'; DROP TABLE runs;--"` → `[]`, table intact) |
| **T-02-07** | Tampering / Repudiation | `policy_hash` | Non-canonical serialization makes the hash unstable, so POLICY-04's audit pin proves nothing. **Demonstrated: `set[str]` reorders across processes; field-declaration order changes the hash.** | mitigate — `sort_keys=True`; `list[str]` + sort validator; `test_hash_is_content_addressed` |
| **T-02-08** | Repudiation | `policy_hash` | An enforcement field added later is accidentally excluded from the payload, so two materially different policies share a hash | mitigate — `test_hashed_key_set_is_pinned` asserts the hashed key set against an explicit literal |
| **T-02-09** | Information Disclosure | `PolicyError` / `ValidationError` | `e.errors()` echoes the rejected `input` value; a wrapped loader error could leak paths | mitigate — `include_url=False`; policy schema carries no credential-shaped field by design; no `sys.path`/`sys.prefix`/env in message text. Naming the user's own policy file is in scope (§Pitfall 7) |
| **T-02-10** | Denial of Service | `list_runs` | Unbounded `limit` materializes the whole table | mitigate — `min(max(limit,1),1000)` |
| **T-02-11** | Information Disclosure | `runs.db` on disk | **Verified: SQLite creates `runs.db`, `runs.db-wal` and `runs.db-shm` at mode `0644`** (umask-dependent). Run history contains workflow ids, policy ids and metrics. | **accept** for v1 with documentation, **or** mitigate with `os.chmod(path, 0o600)` after create. Recommend mitigate — it is one line, and "the control plane's audit trail was world-readable" is a bad sentence in a governance project's README. Note the `-wal`/`-shm` files need it too. |
| **T-02-12** | Spoofing | adapter `CAPABILITIES` | An adapter declares `durable_approval` it does not actually deliver; WORKFLOW-03's gate passes and the guarantee is false | **defer to Phase 7** — CONFORM-01's parametrized suite is the right place. Record here so it is not lost; Phase 2 cannot close it. |

### Known threat patterns for this stack

| Pattern | STRIDE | Standard mitigation |
|---------|--------|---------------------|
| Unsafe YAML deserialization | EoP | `SafeLoader` only (T-02-03) |
| YAML duplicate-key override | Tampering | Custom mapping constructor (T-02-01) |
| Billion-laughs / alias amplification | DoS | Input size cap (T-02-02) |
| Dynamic import from user input | EoP | Allowlist-before-resolution (T-02-04; Phase 1 precedent) |
| SQL injection | Tampering | Parameterized queries (T-02-06) |
| Non-canonical hashing / hash confusion | Repudiation | Sorted-key canonical serialization + pinned key set (T-02-07, T-02-08) |
| Mass assignment / over-posting | Tampering | `extra="forbid"` (POLICY-01) |
| Type-confusion via loose coercion | Tampering | `StrictInt`, `Literal` (Finding 2) |

---

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|-------|---------|---------------|
| A1 | The v1 capability vocabulary should be exactly `{durable_approval, inline_approval}` | Finding 4 | LOW — adding a name later is additive; the `Literal` alias and the frozenset are one edit each. The risk is the opposite direction: over-specifying now creates dead gates. |
| A2 | CrewAI and ag2 provide inline-only approval, LangGraph provides durable | Finding 4 | MEDIUM — sourced from APPROVAL-04/05 and STATE.md's init decision, **not** re-verified against installed frameworks this session (crewai cannot be installed on this host). If ag2's snapshot mechanism turns out to qualify as durable, its `CAPABILITIES` changes — a one-line edit in one file, which is precisely why D-07 put the declaration there. |
| A3 | `requires` should be a required field rather than defaulting to `[]` | Finding 4 | LOW — one character. Flagged explicitly as the place the planner may reasonably disagree with D-08's extension. |
| A4 | `version` belongs outside the hashed payload alongside `policy_id` | Finding 1 | LOW-MEDIUM — this is my extension of D-09, which only asked about `policy_id`. If the user wants a version bump to change the hash, move `version` out of `_IDENTITY_FIELDS` (one line) — but then "did the rules change?" stops being answerable, which is the property the exclusion buys. **Worth a confirmation checkpoint.** |
| A5 | `run_id` is `uuid.uuid4().hex`, generated by the caller | Finding 6 | LOW — the caller-generates part is forced by LANGGRAPH-02's `thread_id = run_id`; only the uuid flavour is discretionary. |
| A6 | `RunRecord`/`StepRecord` are frozen dataclasses, not pydantic models | Standard Stack | LOW — swapping to pydantic later is mechanical; the Protocol signatures do not change. |
| A7 | T-02-11 (0644 store file) should be mitigated rather than accepted | Security Domain | LOW — one `os.chmod` line; the alternative (accept + document) is also defensible at ASVS L1 for a local dev store. |
| A8 | The six-method `RunStore` surface is sufficient and Phase 4's approvals/audit get their own Protocols | Finding 6 | MEDIUM — if Phase 4 discovers approvals need to be transactionally consistent with run status, `RunStore` may need to grow. Mitigated by the fact that adding a method to a `Protocol` is non-breaking for callers; only implementors must catch up, and v1 has one. |

---

## Open Questions

1. **Does a `version` bump change the policy hash? (A4)**
   - What we know: D-09 asked only about `policy_id`. Content-addressing convention (git, OCI, OPA) excludes the *name*; it is silent on an explicit version field because those systems don't have one inside the content.
   - What's unclear: whether the user reads "policy v2" as a new *thing* (hash should move) or as a new *label on possibly-identical rules* (hash should not move).
   - Recommendation: exclude it, as specified in §Code Example 2, and surface it as a one-line confirmation during planning. Excluding buys the "did the rules actually change between versions?" query; including buys nothing the `(policy_id, version)` columns don't already give.

2. **Is `requires: []` acceptable friction on every policy file? (A3)**
   - What we know: D-08's safety argument applies verbatim (a missing capability demand defaults permissive).
   - What's unclear: whether the user values D-08 consistency over YAML terseness here, since `requires` is a demand rather than a limit.
   - Recommendation: required for v1. One-character change if the user disagrees.

3. **Should the workflow registry itself persist, or is it process-local? (not raised anywhere)**
   - What we know: nothing in WORKFLOW-01/02/03 or the Phase 2 success criteria asks for persistence; the registry gates *registration*, and registration happens in Python at import time.
   - What's unclear: Phase 4's `eacp approve <run_id>` CLI runs in a **second process**. It reads the `runs` table (which has `workflow_id` and `policy_hash` as columns) so it does not need the registry — but if the CLI ever needs to resolve `workflow_id → entrypoint`, a process-local registry cannot help it.
   - Recommendation: **keep it process-local for v1** (a plain module dict, like `_BACKENDS`) and make sure the `runs` row is self-contained — which the proposed schema already is, carrying `workflow_id`, `backend_type`, `policy_id` and `policy_hash` as columns rather than as foreign keys into a registry. Flag for the Phase 4 planner rather than solving it here.

4. **Where does the policy→`Policy` object mapping live at runtime? (adjacent, not blocking)**
   - What we know: `Workflow.policy_id` is a string; WORKFLOW-03 needs the actual `Policy` to read `requires`. So `register_workflow` must receive the `Policy` object, not just look up an id.
   - Recommendation: signature `register_workflow(workflow: Workflow, policy: Policy) -> None`, asserting `policy.policy_id == workflow.policy_id`. Avoids a second global registry in this phase. Phase 3's engine can add a policy store if it wants one.

---

## Sources

### Primary (HIGH confidence — executed in this repo's `.venv`, 2026-09-27)
- `.venv/bin/python` 3.12.13 — pydantic 2.12.5 serialization order, `sort_keys` absence, `exclude_unset` behaviour, `StrictInt`/`Decimal`/`strict=True` coercion matrix, `extra="forbid"` error shape, `frozen=True` hashability
- `.venv/bin/python` — PyYAML 6.0.3 duplicate keys, YAML 1.1 scalar resolution, non-mapping roots, `!!python/` tag rejection, alias amplification (220 B → 531,441 nodes)
- `.venv/bin/python` — stdlib `sqlite3` (lib 3.53.2): datetime-adapter deprecation, WAL-in-transaction failure, WAL header persistence, `foreign_keys` default/per-connection scope, `user_version`, `check_same_thread`, `:memory:` per-call behaviour, file permissions, non-parameterizable identifiers, connection benchmark (2000 inserts × 2)
- `.venv/bin/mypy --strict` 2.3.1 — Protocol conformance detection vs `@runtime_checkable` signature-blindness
- `inspect.signature(BaseModel.model_dump_json)` / `pydantic_core.to_json` — `sort_keys` absence
- `opentelemetry-semantic-conventions` 0.66b0 (installed) — `gen_ai.*` attribute names and the `_incubating` module path
- Repo files read this session: `src/eacp/backends.py`, `src/eacp/errors.py`, `src/eacp/adapters/*.py`, `src/eacp/__init__.py`, `pyproject.toml`, `.github/workflows/ci.yml`, `tests/test_packaging.py`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/phases/01-*/01-RESEARCH.md`, `01-SECURITY.md`, `.planning/phases/02-*/02-CONTEXT.md`, `.planning/config.json`

### Secondary (MEDIUM confidence — documentation)
- https://www.openpolicyagent.org/docs/management-bundles — bundle `revision` field kept separate from bundle content; corroborates the id-outside-hash decision
- https://github.com/opsf-org/pct-spec/issues/79 — "content-addressed reference … the hash of an immutable serialised policy representation"; same conclusion from a policy-token spec

### Tertiary (LOW confidence — carried forward, not re-verified this session)
- CLAUDE.md's embedded stack section and `01-RESEARCH.md` — per-framework hook/capability behaviour (LangGraph durable interrupt, CrewAI `hooks`/`HumanInputProvider`, ag2 `ApprovalRequired`). Used only for §Finding 4's capability reasoning, which is tagged MEDIUM for exactly this reason. Not re-verifiable on this host (crewai is uninstallable on macOS x86_64).

---

## Metadata

**Confidence breakdown:**

| Area | Level | Reason |
|------|-------|--------|
| Standard stack | HIGH | Zero new packages; both existing ones read from the live venv |
| Policy schema + hashing | HIGH | Every coercion, ordering and canonicalization claim executed; the full pipeline round-trips |
| YAML safety | HIGH | All four failure modes reproduced with output |
| Entrypoint registry | HIGH | Implemented and exercised, including all rejection paths |
| Store / Protocol | HIGH | Full lifecycle executed including FK, injection, cross-thread, and a real benchmark |
| Capability vocabulary | **MEDIUM** | The *mechanism* is verified; the *per-framework contents* rest on Phase 1 research and requirement wording, not on installed frameworks. See A2. |
| Pitfalls | HIGH | Each pitfall was reproduced, not recalled |
| Security register | MEDIUM-HIGH | T-02-01, -02, -06, -07, -11 demonstrated with output; the rest are design commitments to be verified at execution |

**Research date:** 2026-09-27
**Valid until:** 2026-10-27 (30 days). The phase's entire dependency surface is pinned by `uv.lock` and the stdlib, so nothing here goes stale before then. The one item to re-check if the phase slips: pydantic's `<2.13` cap is crewai-forced and crewai moves fast.
