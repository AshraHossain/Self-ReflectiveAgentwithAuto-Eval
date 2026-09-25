# Enterprise Agent Control Plane (EACP)

## What This Is

EACP is a vendor-agnostic control plane that sits on top of LangGraph, CrewAI, and AutoGen and adds centralized policy enforcement (rate limits, cost budgets, tool restrictions, compliance tags), a unified workflow abstraction across all three frameworks, observability (tracing/metrics/run history), and human-in-the-loop approval gates. It's aimed at platform teams who run agents from multiple frameworks in production and need one governance layer instead of three. The full target spec is captured verbatim in `prompt,md` at the repo root.

## Core Value

A single policy definition can govern a workflow regardless of which framework (LangGraph, CrewAI, or AutoGen) executes it — enforced for real, not just documented.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Policy schema (YAML/JSON): token/cost limits, allowed/forbidden tools, required approval nodes, compliance tags
- [ ] Workflow schema + registry: id, name, backend_type, entrypoint, policy_id
- [ ] Control plane engine: load policies/workflows, validate workflow against policy, route to correct adapter
- [ ] Cost & rate-limit enforcement (token/cost caps enforced at run time, not just declared)
- [ ] Tool-call restriction enforcement (allowed/forbidden tools actually blocked)
- [ ] Human-in-the-loop approval gate: pause a running workflow at a designated node, wait for approve/deny, resume/abort
- [ ] LangGraph adapter (real `langgraph` dependency) wrapping a graph with policy hooks, tracing hooks, an interrupt node for approval
- [ ] CrewAI adapter (real `crewai` dependency) wrapping a crew with per-role policy enforcement and centralized logging
- [ ] AutoGen adapter (real `autogen`/`pyautogen` or `autogen-agentchat` dependency) wrapping a multi-agent conversation with conversation-level policy and tool-call validation
- [ ] Example: compliance-aware contract review workflow on LangGraph (ingestion → risk analysis → recommendation → send-to-counterparty behind an approval gate)
- [ ] Example: sales intelligence crew on CrewAI (researcher/writer/reviewer agents; outbound email volume limit; approval required for flagged phrases)
- [ ] Example: incident response conversation on AutoGen (detector/triage/communicator agents; certain remediation actions blocked without approval)
- [ ] Observability: per-run trace (per-node/per-agent), metrics (latency, token usage, tool-call success rate), run history store (SQLite, pluggable)
- [ ] Benchmark runner: runs the same logical workflow across all three backends and reports latency, token usage, step count, approvals triggered, success/failure — outputs Markdown + JSON/CSV
- [ ] CLI entrypoint per example (run a workflow, see approval prompts, inspect the resulting trace)
- [ ] Docs: README (overview, why a control plane, quickstart, benchmark results), DECISION_FRAMEWORK.md (LangGraph vs CrewAI vs AutoGen tradeoffs), one tutorial per framework
- [ ] Contribution-ready PR description text

### Out of Scope

- Real production deployment (auth, multi-tenancy infra, hosted approval UI) — this is a reference implementation / library, not a hosted SaaS
- A graphical approval UI — CLI approve/deny is sufficient for v1; prompt,md explicitly allows "simple UI or CLI"
- Postgres backend for run history — SQLite only for v1, but store must stay pluggable per prompt,md
- Support for frameworks beyond LangGraph/CrewAI/AutoGen — adapter interface should make adding one easy, but no 4th adapter shipped in v1
- Live LLM calls to paid model APIs required for demos to work — examples must be runnable with a mocked/local LLM or a documented API-key path, so CI and reviewers without keys can still exercise the control-plane logic

## Context

- Solo project intended as a genuine, publishable open-source contribution / portfolio piece — not an internal tool or a learning throwaway. Quality bar: something a platform team could plausibly adopt, and something a framework maintainer could plausibly review favorably.
- Full target spec (architecture, module layout, per-framework example requirements, docs deliverables, output format) already exists at `prompt,md` in the repo root — treat it as the source requirements doc, not just inspiration.
- Repo was empty at project start (LICENSE + prompt,md only) — genuinely greenfield, no existing code or conventions to preserve.
- User wants adapters to use real installed framework libraries (not stubbed imports) so the examples actually run end-to-end — this is a deliberate deviation from prompt,md's "stubbed but realistic" instruction, chosen because a runnable OSS contribution is stronger than a mocked one.
- User wants all three primary use cases from prompt,md (contract review, sales intelligence, incident response), one per framework, matching the worked examples in the spec exactly — no scope-narrowing to a single framework for v1.
- Lazy/YAGNI build discipline is in effect (ponytail): implement exactly what's needed per module, no speculative abstractions beyond the adapter interface prompt,md itself asks for, stub nothing that's supposed to run for real.

## Constraints

- **Language**: Python 3.11+ with type hints — explicit in prompt,md's code style section
- **Dependencies**: Must add real `langgraph`, `crewai`, and an AutoGen package as dependencies since adapters need to be real, not stubbed — pick current stable packages during Phase research, pin versions
- **Runnability without paid keys**: Demos must not hard-require a paid LLM API key to prove the control-plane logic works — support a local/mock model path so reviewers and CI can run examples
- **Persistence**: Run history store must be simple and pluggable (SQLite for v1) — explicit in prompt,md
- **Scope discipline**: Ship the reference architecture + 3 working examples + benchmarks + docs; do not build hosted infra, multi-tenant auth, or a web UI — explicit Out of Scope above

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use real LangGraph/CrewAI/AutoGen libraries in adapters instead of stubs | Prompt,md allows stubs, but a runnable example is far more convincing as a real OSS contribution and portfolio piece | — Pending |
| Ship all 3 use cases (contract review, sales intel, incident response), 1 per framework, for v1 | Matches prompt,md's worked examples exactly; user chose full scope over a narrower single-framework slice | — Pending |
| SQLite for run history, pluggable interface for future backends | Prompt,md explicitly says "keep it simple and pluggable"; avoids standing up Postgres infra for a reference project | — Pending |
| Support a mock/local-model path for demos | Avoids forcing reviewers/CI to hold paid API keys just to exercise policy/approval/tracing logic | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-24 after initialization*
