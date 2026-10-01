# EACP v1 Requirements

Source: `.planning/PROJECT.md` (project context) + `.planning/research/SUMMARY.md` (domain research) + user decisions on AutoGen package and extra scope (2026-09-24).

## v1 Requirements

### PACKAGE — Packaging & Distribution

- [x] **PACKAGE-01**: `pip install eacp && python -c "import eacp"` succeeds with zero agent frameworks installed (core has no LangGraph/CrewAI/ag2 dependency)
- [x] **PACKAGE-02**: Each framework adapter is installable as an optional extra (`eacp[langgraph]`, `eacp[crewai]`, `eacp[ag2]`) with lazy imports inside the adapter module
- [x] **PACKAGE-03**: A committed lockfile pins the full dependency graph for reproducible installs
- [x] **PACKAGE-04**: README documents the platform matrix, including the known macOS x86_64 / CrewAI (`lancedb`) install failure

### POLICY — Policy Schema & Engine

- [x] **POLICY-01**: Policy defined declaratively in YAML with a fixed field schema (no custom DSL), loaded via `yaml.safe_load` only
- [x] **POLICY-02**: Policy schema includes max_tokens_per_run, max_cost_per_day, allowed_tools, forbidden_tools, required_approval_nodes, compliance_tags
- [ ] **POLICY-03**: Policy engine (`decide()`) is pure — no I/O, no clock, no framework imports — and returns a structured `Decision` object (policy id, version, rule, limit, observed value), never a bare boolean
- [ ] **POLICY-04**: Every policy is content-hashed; the hash is pinned to every run record and every audit log entry for reproducibility

### WORKFLOW — Workflow Schema & Registry

- [ ] **WORKFLOW-01**: Workflow schema is id, name, description, backend_type (langgraph|crewai|ag2), entrypoint, policy_id — entrypoint is an opaque pointer to user-authored code, never workflow topology (no nodes/agents/edges fields)
- [ ] **WORKFLOW-02**: Registry validates a workflow's entrypoint against an allowlist at registration time (rejects arbitrary/malicious entrypoints)
- [ ] **WORKFLOW-03**: Registry resolves workflow_id → policy_id and fails loudly at registration if the workflow's backend adapter lacks a capability the policy requires (e.g. a `durable_pause` requirement against an adapter that can't provide it)

### BUDGET — Cost & Rate-Limit Enforcement

- [ ] **BUDGET-01**: Token/cost budget is enforced via pre-call admission (estimate before the call, hard block if it would exceed the limit) — not just checked after the fact
- [ ] **BUDGET-02**: Post-call reconciliation updates actual usage against the pre-call estimate
- [ ] **BUDGET-03**: Daily cost counter is persisted (survives process restart), keyed by policy + UTC date
- [ ] **BUDGET-04**: An independent `max_steps` ceiling bounds runaway loops regardless of token accounting
- [ ] **BUDGET-05**: Every usage reading carries a `usage_source` tag (`provider`|`estimated`|`MISSING`) — usage is never silently coerced to zero

### TOOLS — Tool Restriction

- [ ] **TOOLS-01**: Allowed/forbidden tools are enforced by wrapping the actual callable, not by prompt instructions — a forbidden tool invoked directly (bypassing the model) is still blocked
- [ ] **TOOLS-02**: Tool restriction is enforced across delegation edges (e.g. one agent delegating to another within CrewAI/ag2)

### AUDIT — Compliance Audit Log

- [ ] **AUDIT-01**: Every policy decision (allow/deny/warn) is appended to an audit log distinct from the debug trace, recording policy id + version, rule, limit, observed value, and timestamp
- [ ] **AUDIT-02**: Audit log is append-only

### APPROVAL — Human-in-the-Loop

- [ ] **APPROVAL-01**: Approval gate is a persisted `ApprovalRequest` row owned by the control plane (never a blocking `input()` call inside a framework hook)
- [ ] **APPROVAL-02**: `eacp approve <run_id>` / `eacp deny <run_id>` CLI resolves a pending approval from a separate process while the run is still paused
- [ ] **APPROVAL-03**: Default is deny — an unresolved or denied approval halts the run, it never silently proceeds
- [ ] **APPROVAL-04**: LangGraph adapter provides durable pause/resume (process may exit while awaiting approval; resume re-enters the workflow from the checkpoint)
- [ ] **APPROVAL-05**: CrewAI and ag2 adapters provide inline (in-process, blocking) approval for v1; each adapter declares its actual HITL capability (durable|inline) rather than faking durable support

### TRACE — Observability

- [ ] **TRACE-01**: Every run produces a per-node/per-agent trace: latency, token usage, tool-call outcomes
- [ ] **TRACE-02**: Trace spans use OpenTelemetry GenAI semantic-convention attribute names (`gen_ai.*`) so the storage format is exportable later without a rewrite
- [ ] **TRACE-03**: Run history (run_id, workflow_id, backend_type, timestamps, status, metrics) is persisted to a pluggable store, with a SQLite implementation for v1
- [ ] **TRACE-04**: On LangGraph, a resumed (post-approval) run's token/span counts equal what a single uninterrupted pass would produce (no double-counting from node replay)

### LANGGRAPH — LangGraph Adapter

- [ ] **LANGGRAPH-01**: Adapter wraps a LangGraph graph, injecting policy checks at the model-client and tool-call seams
- [ ] **LANGGRAPH-02**: Adapter provides a durable interrupt-only gate node (side-effecting work lives in the following node, not the gate node itself) backed by a SQLite checkpointer keyed on `thread_id = run_id`

### CREWAI — CrewAI Adapter

- [ ] **CREWAI-01**: Adapter wraps a CrewAI crew using `crewai.hooks` (`before_tool_call`/`before_llm_call`) for policy enforcement per agent role, not observation-only callbacks
- [ ] **CREWAI-02**: Adapter provides centralized logging/tracing via CrewAI's event bus
- [ ] **CREWAI-03**: Run identity is propagated correctly across CrewAI's thread-based execution paths (no cross-run contamination of policy state)

### AG2 — AutoGen-lineage (ag2) Adapter

- [ ] **AG2-01**: Adapter targets the `ag2` package (not `autogen`/`pyautogen`/`autogen-agentchat`), pinned to an exact version
- [ ] **AG2-02**: Adapter wraps an ag2 multi-agent conversation using `middleware`/`observers`/`hitl_hook` for conversation-level policy and tool-call validation

### CONFORM — Cross-Adapter Conformance

- [ ] **CONFORM-01**: A parametrized test suite asserts the same policy produces the same allow/deny/budget-halt/approval behavior across all three adapters (LangGraph, CrewAI, ag2)

### EXAMPLES — Worked Examples

- [ ] **EXAMPLES-01**: Contract review example (LangGraph): ingestion → risk analysis → recommendation → send-to-counterparty behind an approval gate; runnable with a mock LLM, no paid API key required
- [ ] **EXAMPLES-02**: Sales intelligence example (CrewAI): researcher/writer/reviewer agents; outbound email volume limit; approval required when flagged phrases are present; runnable keyless
- [ ] **EXAMPLES-03**: Incident response example (ag2): detector/triage/communicator agents; certain remediation actions blocked without approval; runnable keyless
- [ ] **EXAMPLES-04**: Each example has a CLI entrypoint and demonstrates three scenarios: policy-approved run, policy-denied/violation run, and human-approval run

### BENCH — Benchmark Runner

- [ ] **BENCH-01**: Benchmark runner executes the same logical workflow across all three backends and collects latency, token usage, step count, approvals triggered, success/failure
- [ ] **BENCH-02**: Output is Markdown summary plus JSON/CSV for further analysis
- [ ] **BENCH-03**: Benchmark defaults to the mock LLM (deterministic, keyless); results explicitly document that token/latency numbers are synthetic under the mock and note the framework-native scaffold as a confound

### DOCS — Documentation & Contribution

- [ ] **DOCS-01**: Top-level README: overview, why a control plane, supported frameworks, architecture description, quickstart, benchmark instructions + sample results, contribution guide
- [ ] **DOCS-02**: `docs/DECISION_FRAMEWORK.md`: LangGraph vs CrewAI vs ag2 tradeoffs, including the AdapterCapabilities matrix and the AutoGen-package-naming situation, grounded in this project's own measured numbers
- [ ] **DOCS-03**: One tutorial per framework (`docs/TUTORIAL_LANGGRAPH.md`, `docs/TUTORIAL_CREWAI.md`, `docs/TUTORIAL_AG2.md`): define a policy, define/register a workflow, run it (with approval gate where applicable), inspect trace/metrics
- [ ] **DOCS-04**: Contribution-ready PR description text: motivation, architecture summary, governance/observability/interoperability value, invitation for maintainer review

## v2 (Deferred)

- Dry-run/shadow policy mode (`enforce`|`warn`|`off` per rule) — user deferred; strong candidate for the first v2 milestone since research flags it as high-credibility-per-line
- Control-plane overhead benchmark (ms/% vs. an unwrapped run) — user deferred; BENCH-03 already documents the mock-LLM limitation so this isn't blocking
- Per-tenant policy scoping (tenant → workflow → default resolution) — user deferred; ~30 lines per research, revisit if compliance-tag enforcement becomes load-bearing
- Durable (checkpointed) approval on CrewAI and ag2 — both frameworks currently support only inline/blocking or snapshot-at-message-boundary approval; true durable pause/resume on these backends is a framework-level limitation, not a v1 scope cut
- Compliance tags gating enforcement beyond documentation (e.g. automatic trace redaction, tag-driven tool allowlists) — tags are captured and auditable in v1 but don't yet drive additional automated behavior
- Adapter-authoring guide targeting Microsoft Agent Framework as a worked 4th-adapter example
- A 4th framework adapter (e.g. Microsoft Agent Framework)
- Guardrail/PII-detection hook interface with a reference implementation
- Prometheus metrics endpoint, Postgres/ClickHouse run-history backend
- Hosted approval web UI

## Out of Scope

- Real production deployment (auth, multi-tenancy infrastructure, hosted UI) — this is a reference implementation / library, not a hosted SaaS
- Requiring a paid LLM API key for any example or test to run — all three frameworks ship first-class scripted fake/mock model clients, used throughout
- A neutral cross-framework workflow-authoring DSL — the project unifies the governance plane (policy, approval, trace, audit) only; workflows stay authored natively in each framework, per research's strongest finding
- Reimplementing framework internals (e.g. forking CrewAI's executor to add checkpointing) to fake capabilities a framework doesn't natively support

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PACKAGE-01 | Phase 1 | Complete |
| PACKAGE-02 | Phase 1 | Complete |
| PACKAGE-03 | Phase 1 | Complete |
| PACKAGE-04 | Phase 1 | Complete |
| POLICY-01 | Phase 2 | Complete |
| POLICY-02 | Phase 2 | Complete |
| POLICY-04 | Phase 2 | Pending |
| WORKFLOW-01 | Phase 2 | Pending |
| WORKFLOW-02 | Phase 2 | Pending |
| WORKFLOW-03 | Phase 2 | Pending |
| TRACE-03 | Phase 2 | Pending |
| POLICY-03 | Phase 3 | Pending |
| BUDGET-01 | Phase 3 | Pending |
| BUDGET-02 | Phase 3 | Pending |
| BUDGET-03 | Phase 3 | Pending |
| BUDGET-04 | Phase 3 | Pending |
| BUDGET-05 | Phase 3 | Pending |
| AUDIT-01 | Phase 4 | Pending |
| AUDIT-02 | Phase 4 | Pending |
| APPROVAL-01 | Phase 4 | Pending |
| APPROVAL-02 | Phase 4 | Pending |
| APPROVAL-03 | Phase 4 | Pending |
| LANGGRAPH-01 | Phase 5 | Pending |
| LANGGRAPH-02 | Phase 5 | Pending |
| APPROVAL-04 | Phase 5 | Pending |
| TOOLS-01 | Phase 5 | Pending |
| TRACE-01 | Phase 5 | Pending |
| TRACE-02 | Phase 5 | Pending |
| TRACE-04 | Phase 5 | Pending |
| CREWAI-01 | Phase 6 | Pending |
| CREWAI-02 | Phase 6 | Pending |
| CREWAI-03 | Phase 6 | Pending |
| APPROVAL-05 | Phase 6 | Pending |
| TOOLS-02 | Phase 6 | Pending |
| AG2-01 | Phase 7 | Pending |
| AG2-02 | Phase 7 | Pending |
| CONFORM-01 | Phase 7 | Pending |
| EXAMPLES-01 | Phase 8 | Pending |
| EXAMPLES-02 | Phase 8 | Pending |
| EXAMPLES-03 | Phase 8 | Pending |
| EXAMPLES-04 | Phase 8 | Pending |
| BENCH-01 | Phase 9 | Pending |
| BENCH-02 | Phase 9 | Pending |
| BENCH-03 | Phase 9 | Pending |
| DOCS-01 | Phase 10 | Pending |
| DOCS-02 | Phase 10 | Pending |
| DOCS-03 | Phase 10 | Pending |
| DOCS-04 | Phase 10 | Pending |

**Coverage: 48/48 v1 requirements mapped, 0 orphans.**

---
*Requirements defined: 2026-09-24*
*Traceability added: 2026-09-25 after roadmap creation*
