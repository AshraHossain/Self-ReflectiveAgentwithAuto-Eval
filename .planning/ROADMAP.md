# Roadmap: Enterprise Agent Control Plane (EACP)

## Overview

EACP is built bottom-up: a stable, framework-free foundation (schema, policy engine, budget ledger, approval service) proven entirely without any agent framework installed, then three real framework adapters wired to that foundation one at a time — LangGraph first because it has the richest native support, CrewAI second because it's the hardest human-in-the-loop case and forces the capability-tier design to exist honestly, then ag2 third to prove the adapter interface (extracted from the first two) generalizes. Examples, a benchmark runner, and docs come last, once there's real, adapter-verified behavior to demonstrate and measure rather than aspirational claims. This is a deliberate horizontal-layers build (chosen over vertical MVP slices) because the dependency order here is real: the approval gate's data contract has to exist before any adapter can be honestly built against it, and building one adapter at a time is what turns "vendor-agnostic" from an assertion into something a conformance suite proves.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Stack Decision, Scaffold & Packaging** - Installable core with zero framework lock-in and pinned, reproducible extras (completed 2026-09-26)
- [x] **Phase 2: Core Schema, Registry & Stores** - Policies and workflows are declared, validated, and stored consistently (completed 2026-10-02)
- [ ] **Phase 3: Policy Engine, Budget Ledger & Mock LLM** - Enforcement logic proven correct with zero frameworks installed
- [ ] **Phase 4: Approval Service, Audit Log & CLI** - Human-in-the-loop gate and compliance audit trail, framework-independent
- [ ] **Phase 5: LangGraph Adapter & Tracer** - First real framework integration with durable pause/resume
- [ ] **Phase 6: CrewAI Adapter** - Second adapter; forces the capability-tier design via the hardest HITL case
- [ ] **Phase 7: Adapter Interface Extraction & ag2 Adapter** - Interface generalized and proven by a third, different framework
- [ ] **Phase 8: Three Worked Examples** - Contract review, sales intel, incident response — runnable keyless
- [ ] **Phase 9: Benchmark Runner** - Cross-backend overhead and behavioral comparison
- [ ] **Phase 10: Documentation & Contribution** - README, decision framework, tutorials, PR description

## Phase Details

### Phase 1: Stack Decision, Scaffold & Packaging

**Goal**: The project can be installed by anyone, with zero framework lock-in, on a pinned and reproducible dependency set.
**Depends on**: Nothing (first phase)
**Requirements**: PACKAGE-01, PACKAGE-02, PACKAGE-03, PACKAGE-04
**Success Criteria** (what must be TRUE):

  1. `pip install eacp && python -c "import eacp"` succeeds with zero LangGraph/CrewAI/ag2 packages installed
  2. `pip install eacp[langgraph]` / `eacp[crewai]` / `eacp[ag2]` each install cleanly as isolated extras with lazy imports
  3. A committed lockfile reproduces the same dependency set on a fresh install
  4. README states the macOS x86_64 / CrewAI(`lancedb`) install limitation before a user hits it

**Plans**: 3 plans
Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Manifest, README platform matrix, framework-free package skeleton, committed `uv.lock` (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Lazy backend loader, three placeholder adapters, packaging test suite (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — GitHub Actions 8-cell core + extras matrix gate, confirmed green (wave 3)

### Phase 2: Core Schema, Registry & Stores

**Goal**: Policies and workflows are declared, validated, and stored the same way regardless of which framework will eventually run them.
**Depends on**: Phase 1
**Requirements**: POLICY-01, POLICY-02, POLICY-04, WORKFLOW-01, WORKFLOW-02, WORKFLOW-03, TRACE-03
**Success Criteria** (what must be TRUE):

  1. A policy YAML file with an unknown/forbidden field is rejected at load time (`safe_load` + fixed schema, no DSL)
  2. Every policy is content-hashed and that hash is retrievable and stable for identical policy content
  3. A workflow entrypoint not on the allowlist is rejected at registration time, not at run time
  4. Run history can be written to and read back from the SQLite store via its `Protocol` interface with zero framework code imported

**Plans**: 3/3 plans complete
Plans:
**Wave 1** *(the two halves share nothing — run them in parallel)*

- [x] 02-01-PLAN.md — Exception types, capability vocabulary, hardened YAML loader, strict `Policy` schema, canonical content hash (wave 1)
- [x] 02-02-PLAN.md — Test/type-check gates, `RunStore` Protocol, `SQLiteRunStore` with query hardening and file permissions (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-03-PLAN.md — Per-adapter `CAPABILITIES`, entrypoint allowlist, `Workflow` schema, WORKFLOW-03 capability gate (wave 2)

### Phase 3: Policy Engine, Budget Ledger & Mock LLM

**Goal**: The policy decision engine and cost enforcement work correctly and are fully tested before any framework is involved.
**Depends on**: Phase 2
**Requirements**: POLICY-03, BUDGET-01, BUDGET-02, BUDGET-03, BUDGET-04, BUDGET-05
**Success Criteria** (what must be TRUE):

  1. `decide()` returns a structured `Decision` (policy id, version, rule, limit, observed) for both an allowed and a denied case, with no framework or I/O dependency
  2. A run whose next call would exceed `max_cost_per_day` is blocked before that call executes (pre-call admission), not only after
  3. The daily cost counter survives a process restart and continues accumulating correctly
  4. A mock LLM emits scripted tool calls and non-zero usage, exercised by an automated test with no API key present

**Plans**: TBD

### Phase 4: Approval Service, Audit Log & CLI

**Goal**: A run can be paused for human approval and every policy decision is durably recorded, independent of any framework.
**Depends on**: Phase 3
**Requirements**: AUDIT-01, AUDIT-02, APPROVAL-01, APPROVAL-02, APPROVAL-03
**Success Criteria** (what must be TRUE):

  1. `eacp approve <run_id>` resolves a pending `ApprovalRequest` from a second process while the first process that created it is still waiting
  2. An unresolved approval halts the run rather than silently continuing (default-deny verified by test)
  3. Every policy decision (allow/deny/warn) appears in the append-only audit log with policy id, version, rule, limit, and observed value
  4. Audit log entries cannot be edited or deleted through the store's public interface

**Plans**: TBD

### Phase 5: LangGraph Adapter & Tracer

**Goal**: A real LangGraph workflow runs under EACP's policy, budget, and approval enforcement, with a durable pause/resume approval flow.
**Depends on**: Phase 4
**Requirements**: LANGGRAPH-01, LANGGRAPH-02, APPROVAL-04, TOOLS-01, TRACE-01, TRACE-02, TRACE-04
**Success Criteria** (what must be TRUE):

  1. A LangGraph workflow that calls a forbidden tool directly (bypassing the model) is blocked by the wrapped tool object, not by a prompt instruction
  2. A workflow paused at an approval gate can be resumed after the process exits and restarts, using the persisted checkpoint
  3. Token/span counts after a resumed run equal what a single uninterrupted pass would have produced (no node-replay double-counting)
  4. Every node in an example run appears in the trace store with latency, token usage, and tool-call outcome, using `gen_ai.*` attribute names

**Plans**: TBD

### Phase 6: CrewAI Adapter

**Goal**: A real CrewAI crew runs under the same policy/budget/approval enforcement as LangGraph, proving the control plane isn't LangGraph-shaped.
**Depends on**: Phase 5
**Prerequisite**: A Docker/colima Linux container for local dev — this development machine is a genuine Intel Mac (x86_64) and CrewAI's `lancedb` dependency has no macOS x86_64 wheel or sdist at any version (verified 0.29.0–0.39.0), so CrewAI cannot be installed or run directly on this host. Set up the container before starting this phase, not mid-phase. See `.planning/STATE.md` Blockers/Concerns.
**Requirements**: CREWAI-01, CREWAI-02, CREWAI-03, APPROVAL-05, TOOLS-02
**Success Criteria** (what must be TRUE):

  1. A CrewAI crew with a forbidden tool assigned to one role has that tool call blocked via `before_tool_call`, including when delegated to another agent
  2. Two concurrent CrewAI runs enforce their own policies independently (no cross-run contamination from CrewAI's global hook registry)
  3. An approval-required action in a CrewAI crew pauses the crew and is resolved through the same `eacp approve` CLI used for LangGraph

**Plans**: TBD

### Phase 7: Adapter Interface Extraction & ag2 Adapter

**Goal**: The adapter interface is proven general by fitting a third, architecturally different framework without changing the interface.
**Depends on**: Phase 6
**Requirements**: AG2-01, AG2-02, CONFORM-01
**Success Criteria** (what must be TRUE):

  1. A real ag2 multi-agent conversation runs under EACP policy enforcement using ag2's middleware/observer/hitl_hook seams
  2. A policy that requires durable pause (a capability ag2 doesn't have) fails loudly at registration against the ag2 adapter, rather than silently degrading
  3. The same policy produces the same allow/deny/budget-halt outcome across LangGraph, CrewAI, and ag2 in a parametrized conformance test
  4. Every adapter's declared `durable_approval`/`inline_approval` capability is honest: for each adapter claiming `durable_approval`, a run paused by it genuinely survives a process exit and resumes correctly (T-02-12, transferred from Phase 2 — `register_workflow`'s capability gate only checks a backend's *declaration* against a policy's *requirement*; nothing before this phase can verify the declaration against actual adapter behavior, since no adapter executes a real workflow until Phase 5+)

**Plans**: TBD

### Phase 8: Three Worked Examples

**Goal**: A reviewer can run all three worked examples end-to-end without an API key and see policy enforcement in action.
**Depends on**: Phase 7
**Requirements**: EXAMPLES-01, EXAMPLES-02, EXAMPLES-03, EXAMPLES-04
**Success Criteria** (what must be TRUE):

  1. The contract-review example (LangGraph) completes an approve scenario, a deny/violation scenario, and a human-approval scenario, all keyless
  2. The sales-intel example (CrewAI) enforces its outbound email volume limit and its flagged-phrase approval requirement
  3. The incident-response example (ag2) blocks a restricted remediation action without approval and allows it once approved
  4. Each example's CLI entrypoint produces a trace and run record inspectable via `eacp` commands

**Plans**: TBD

### Phase 9: Benchmark Runner

**Goal**: A reviewer can measure how much overhead the control plane adds and see comparable behavioral data across all three backends.
**Depends on**: Phase 8
**Requirements**: BENCH-01, BENCH-02, BENCH-03
**Success Criteria** (what must be TRUE):

  1. The benchmark runner runs the same logical workflow across all three backends against the mock LLM and produces a Markdown summary plus JSON/CSV output
  2. The benchmark report states the mock-LLM limitation on latency/token numbers explicitly rather than presenting them as ground truth
  3. The report includes step count, approvals triggered, and success/failure rate per backend for the same workflow

**Plans**: TBD

### Phase 10: Documentation & Contribution

**Goal**: A framework maintainer or platform-team engineer can read the docs and understand why this exists, how it works, and how to extend it.
**Depends on**: Phase 9
**Requirements**: DOCS-01, DOCS-02, DOCS-03, DOCS-04
**Success Criteria** (what must be TRUE):

  1. README's quickstart takes a reader from `pip install` to a running keyless example in under five commands
  2. `docs/DECISION_FRAMEWORK.md`'s capability matrix reflects what Phases 5-7 actually built, grounded in this project's own measured numbers
  3. Each of the three tutorials (LangGraph/CrewAI/ag2) walks through defining a policy, registering a workflow, running it, and inspecting the resulting trace
  4. The PR description text is ready to paste into a real pull request without further editing

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Stack Decision, Scaffold & Packaging | 3/3 | Complete   | 2026-09-26 |
| 2. Core Schema, Registry & Stores | 3/3 | Complete   | 2026-10-02 |
| 3. Policy Engine, Budget Ledger & Mock LLM | 0/TBD | Not started | - |
| 4. Approval Service, Audit Log & CLI | 0/TBD | Not started | - |
| 5. LangGraph Adapter & Tracer | 0/TBD | Not started | - |
| 6. CrewAI Adapter | 0/TBD | Not started | - |
| 7. Adapter Interface Extraction & ag2 Adapter | 0/TBD | Not started | - |
| 8. Three Worked Examples | 0/TBD | Not started | - |
| 9. Benchmark Runner | 0/TBD | Not started | - |
| 10. Documentation & Contribution | 0/TBD | Not started | - |

**Note on phase count vs. granularity setting:** config.json granularity is "standard" (typically 4-6 phases). This roadmap uses 10 because the project has three genuinely separate, sequentially-gated framework integrations (each requiring the approval/policy foundation to exist first) plus distinct examples/benchmark/docs deliverables — collapsing them would either violate real dependency order or produce phases spanning unrelated frameworks with no coherent single success criterion. Matches `.planning/research/SUMMARY.md`'s "Implications for Roadmap" section exactly.
