# Phase 2: Core Schema, Registry & Stores - Context

**Gathered:** 2026-09-27
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers the vendor-neutral data layer of the control plane: a declarative
policy schema that is validated and content-hashed, a workflow registry that validates
entrypoints against an allowlist and refuses registrations whose policy demands a
capability the target backend cannot provide, and a pluggable run-history store with a
SQLite implementation.

It does **not** enforce policy at runtime (Phase 3), does not implement any adapter
(Phases 5-7), and does not execute a workflow. It defines the contracts those phases
consume.

**Hard constraint inherited from Phase 1:** none of this code may import langgraph,
crewai, or ag2. PACKAGE-01's CI gate asserts `import eacp` pulls in no framework, and it
runs on every push. Policy/registry/store code is core, not adapter code.

Requirements: POLICY-01, POLICY-02, POLICY-04, WORKFLOW-01, WORKFLOW-02, WORKFLOW-03, TRACE-03.

</domain>

<decisions>
## Implementation Decisions

### User-decided (locked)

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

### Claude's discretion (defaulted, not user-decided — change freely if research disagrees)

The user explicitly delegated these three after weighing reversibility. Each default is
recorded so the planner has a definite starting point, not so it is treated as locked.

- **D-08: Policy schema is strict in both directions.** pydantic with
  `extra="forbid"` (forced by POLICY-01's success criterion), and every POLICY-02 limit
  field is **required with no default**. A policy omitting `max_cost_per_day` is invalid,
  not unlimited. Rationale: silently defaulting a missing budget to infinity is how a
  governance tool stops governing, and the project's core value is "enforced for real."
  Direction of safety: relaxing required→optional later is non-breaking; tightening is
  breaking.

- **D-09: The policy hash covers the canonicalized model, not raw YAML bytes.**
  Serialize the validated pydantic model to canonical JSON with sorted keys, then
  SHA-256. Rationale: reformatting or reordering a YAML file must not change a policy's
  identity. Open sub-questions for research: whether an absent optional field hashes
  identically to an explicit null, and whether `policy_id` itself is inside the hashed
  payload (it probably should not be — the hash identifies *content*, the id names it).

- **D-10: The entrypoint allowlist is explicit registration, mirroring `_BACKENDS`.**
  A workflow's `entrypoint` is only resolvable if it was explicitly registered, exactly
  as Phase 1's `_BACKENDS` dict gates adapter imports: allowlist lookup strictly before
  any resolution, so a caller-supplied string is never interpolated into an import
  target. Rejected: import-path prefix matching (bypassable) and Python entry-point
  groups (any installed package could inject one).


### Resolved after research (2026-09-27) — answers to 02-RESEARCH.md Open Questions

- **D-11: `version` is excluded from the policy hash, alongside `policy_id`.** Only the
  enforceable rules are hashed. Rationale: if bumping `version` changed the hash, the
  hash could no longer answer the one question it exists to answer — "did the rules
  actually change between v1 and v2?" Excluding both makes that a string comparison.
  Nothing is lost: the `runs` row carries `policy_id` and `policy_hash` as separate
  columns.

- **D-12: `requires` is a required field on every policy, not defaulted to `[]`.**
  I initially judged that D-08's safety argument did not transfer here — an omitted
  `requires` means "no special capability needed," which is not dangerous the way an
  omitted budget is. That was wrong. Consider a policy with a non-empty
  `required_approval_nodes` and no `requires`: registered against ag2 (snapshot-only),
  its approval silently is not durable, and the author never had to confront the
  choice. Same failure shape as the budget case — absence means permissive, quietly.
  Forcing `requires: [durable_approval]` or `requires: [inline_approval]` makes the
  durability decision explicit. Cost: one line in every policy file, including the
  common `requires: []` case.

- **D-13: the workflow registry is process-local for v1, not persisted.** Registration
  happens in-process at startup. Rationale: the `runs` table is deliberately
  self-contained — `workflow_id`, `backend_type`, `policy_id` and `policy_hash` are
  columns, not foreign keys — so Phase 4's second-process approval CLI reads run history
  without ever needing the registry. Persisting it would add a schema and a sync problem
  for no v1 consumer. Flagged for the Phase 4 planner.

### Amendments to earlier defaults, forced by research evidence

- **D-08 amended:** use field-level `StrictInt` on counter fields, NOT model-level
  `strict=True`. Model-level strict correctly blocks YAML `yes` → `int 1`, but also
  rejects a plain YAML `100` for a `Decimal` field. Lax `Decimal` already rejects
  booleans on its own.
- **D-09 sharpened — this one is a real defect in my original default.**
  `model_dump_json()` has no `sort_keys` parameter and emits keys in **field-declaration
  order**, so reorganising the `Policy` class body would silently change every policy
  hash. Worse, `set[str]` serializes in **nondeterministic order across processes**
  (three runs, three orders). Canonical form must be
  `json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))`,
  and tag/tool collections must be `list[str]` with a sort+dedupe validator, never
  `set[str]`. Also: never pass `exclude_unset`/`exclude_defaults`/`exclude_none`, or an
  unset optional stops hashing identically to an explicit `None`.
- **New requirement not in any earlier decision:** `yaml.safe_load` silently accepts
  **duplicate keys, last one wins** — verified. PyYAML collapses them before pydantic,
  so `extra="forbid"` cannot see it. In a policy loader that is a limit-override
  primitive, so a `SafeLoader` subclass rejecting duplicate keys is mandatory, not
  optional. Pair with a byte cap (a 220-byte alias bomb expanded to 531,441 nodes in
  0.06 s).
- **`@runtime_checkable` must NOT be used on the `RunStore` Protocol** — it is
  signature-blind and returned `True` for a class with entirely wrong arities. Static
  checking via a one-line `store: RunStore = SQLiteRunStore(...)` probe under
  `mypy --strict` catches what it cannot.

### Established patterns Phase 2 must follow (from Phase 1, not re-litigated)

- `registry.py` is unclaimed and is this phase's natural home — `backends.py` was
  deliberately named to leave it free.
- Allowlist lookup **before** resolution, with `ValueError` on an unknown key.
- Errors subclass appropriately and carry no filesystem paths, env vars, or venv
  locations in their message text (T-01-05).
- `src/` layout; tests import the installed package, never via `sys.path` or a
  `conftest.py` hack (D-02).
- Every dependency range upper-bounded.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source spec
- `prompt.md` (repo root) — module layout (`core/engine/` = policy engine, workflow
  registry, execution router, cost/rate-limit manager; `observability/` = run history
  store), Python 3.11+ with type hints

### Project planning
- `.planning/REQUIREMENTS.md` §POLICY, §WORKFLOW, §TRACE — the 7 requirements this phase
  satisfies, with their exact wording (POLICY-01 names `yaml.safe_load` and "no custom
  DSL"; WORKFLOW-01 forbids nodes/agents/edges fields on the workflow schema)
- `.planning/ROADMAP.md` §Phase 2 — goal and the 4 success criteria
- `.planning/PROJECT.md` — "SQLite for run history, pluggable interface" is a locked
  project-level decision
- `.planning/STATE.md` §Decisions — the init decision that uniform durable pause/resume
  across all three frameworks is architecturally impossible, resolved by a declared
  `AdapterCapabilities` matrix that fails loudly at registration. WORKFLOW-03 is the
  implementation of that decision.

### Phase 1 artifacts (the contracts this phase extends)
- `src/eacp/backends.py` — the `_BACKENDS` allowlist pattern this phase mirrors, and
  `load_backend_module`, which the registry calls to read `CAPABILITIES`
- `src/eacp/errors.py` — `MissingExtraError(ImportError)`; new errors join it here
- `.planning/phases/01-stack-decision-scaffold-packaging/01-CONTEXT.md` — D-01 to D-05
- `.planning/phases/01-stack-decision-scaffold-packaging/01-SECURITY.md` — the threat
  register this phase extends. **Allocate Phase 2 threat IDs from a single phase-wide
  sequence**; Phase 1 collided `T-01-03` and `T-01-04` across plans by numbering
  per-plan.
- `.planning/phases/01-stack-decision-scaffold-packaging/01-02-SUMMARY.md` — records
  that `registry.py` was left free for this phase

### Research
- `.planning/research/STACK.md` — `pydantic>=2.11,<2.13` (hard cap from crewai-core),
  stdlib `sqlite3` behind a Protocol rather than SQLAlchemy, stdlib `csv`/`json`
- `.planning/research/ARCHITECTURE.md`
- `.planning/research/PITFALLS.md`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/eacp/backends.py` (52 lines) — `_BACKENDS` allowlist, `available_backends()`,
  `load_backend_module()`. The registry consumes `load_backend_module` to reach each
  adapter's `CAPABILITIES`. Its allowlist-before-resolution shape is the template for
  the entrypoint allowlist (D-10).
- `src/eacp/errors.py` (2 lines) — `MissingExtraError(ImportError)`. New exception types
  belong here.
- `src/eacp/adapters/*.py` — three placeholders exporting `BACKEND` and
  `FRAMEWORK_VERSION`. D-07 adds `CAPABILITIES` to that same shape. Their bodies are
  filled in Phases 5/6/7; this phase only extends the constant surface.

### Established Patterns
- Allowlist dict → `ValueError` on miss → resolve only allowlisted values
- Module constants as the adapter's declarative surface (`BACKEND`,
  `FRAMEWORK_VERSION`, now `CAPABILITIES`)
- `importlib.metadata.version()` for version reads, never `getattr(mod, "__version__")`
  — langgraph exposes no `__version__` and the getattr pattern silently returned
  "unknown"

### Integration Points
- **Registry → backends:** `registry.py` calls `load_backend_module(backend_type)` to
  read `CAPABILITIES` during registration. This is the only coupling between the two.
- **Phase 3 (policy engine)** consumes the validated policy model and its content hash.
- **Phases 5/6/7 (adapters)** consume the sync `RunStore` Protocol and declare
  `CAPABILITIES`.
- **Phase 1 CI** gates every commit here: if any Phase 2 module imports a framework at
  module scope, the `core` job's `find_spec` assertion fails on both OSes.

</code_context>

<specifics>
## Specific Ideas

No UI surface in this phase. The only user-facing artifacts are the policy YAML format
and the exceptions raised on invalid input — both of which should fail with messages
that name the offending field and the allowed values, consistent with Phase 1's
`MissingExtraError` telling the user the exact `pip install` command to run.

</specifics>

<deferred>
## Deferred Ideas

- **Offline capability-matrix rendering** — D-07's accepted consequence. If docs need a
  full matrix without installing all three extras, generate it in CI (where all extras
  are present) rather than adding a central runtime table.
- **Per-tenant policy scoping** — already deferred to v2 at requirements time.
- **A second store backend (Postgres)** — the Protocol makes it possible; v1 ships
  SQLite only, per PROJECT.md.

</deferred>

---

*Phase: 2-Core Schema, Registry & Stores*
*Context gathered: 2026-09-27*
