# Feature Research

**Domain:** Agent control plane / agent governance layer for multi-framework agent orchestration (LangGraph, CrewAI, AutoGen)
**Researched:** 2026-09-24
**Confidence:** MEDIUM-HIGH (framework capability claims verified against official docs = HIGH; market/competitor feature claims from vendor pages and secondary analysis = MEDIUM)

## Context

This project is a **solo open-source reference implementation**, not a SaaS. So "table stakes" here means two different audiences, and they want different things:

- **Platform team evaluating adoption** — will dismiss the project if the governance primitives aren't *actually enforced*, aren't auditable, and can't be rolled out safely.
- **Framework maintainer reviewing a contribution** — will dismiss the project if it's a lowest-common-denominator wrapper that papers over real semantic differences between the three frameworks.

The single biggest research finding is that these two audiences pull in **opposite** directions on one specific feature: the unified approval gate. See [Critical Feasibility Flags](#critical-feasibility-flags).

---

## Critical Feasibility Flags

Read this before the feature tables. Three items in the current `.planning/PROJECT.md` scope are, per research, not deliverable as literally written.

### FLAG 1 — "Unified approval gate: pause a running workflow, wait for approve/deny, resume/abort" is not uniformly implementable across the three frameworks

Confidence: **HIGH** (verified against official framework docs)

| Framework | Pause/resume reality | Source confidence |
|-----------|----------------------|-------------------|
| **LangGraph** | True durable suspend/resume. `interrupt()` + `Command(resume=...)` with a checkpointer. Approve / edit / reject / respond are first-class decision types. Requires a configured checkpointer to persist state across the interrupt. | HIGH — official LangChain docs |
| **CrewAI** | `human_input=True` on a Task gives a **blocking, inline** prompt before the agent delivers its final answer — not a suspend. Checkpointing exists (`Flow.kickoff(from_checkpoint=..., restore_from_state_id=...)`) and captures crew/flow/agent state + kickoff inputs + event history, but community reports indicate pause/resume is available at **agent-task level, not arbitrary flow-node level**. | MEDIUM-HIGH — CrewAI docs + community threads |
| **AutoGen (`autogen-agentchat`)** | Official docs state directly: when `UserProxyAgent` is called during a run it "blocks the execution of the team until the user provides feedback or errors out. This will hold up the team's progress and **put the team in an unstable state that cannot be saved or resumed**." The documented pattern is *terminate the run* (via `HandoffTermination` / `TextMentionTermination`) → `save_state()` → persist → `load_state()` and resume as a **new run** carrying the feedback. There is no mid-run checkpoint API. | HIGH — official AutoGen docs |

**What this means:** a single `approve_and_resume(run_id)` API that behaves identically on all three backends is a lie the abstraction cannot keep. Shipping it anyway is precisely the "leaky abstraction / lowest common denominator" failure a framework maintainer will call out in review.

**Recommended reshape for v1** — make the difference explicit in the abstraction instead of hiding it. Two declared approval modes, and each adapter declares which it supports:

- `mode: inline` — execution blocks in-process at the gate; approve/deny resolves immediately. Supported by all three. Trivially correct.
- `mode: durable` — run is suspended, state persisted, process may exit, resume later by `run_id`. Supported natively by LangGraph; supported on AutoGen only via terminate→save→resume (so the "resume" starts a new run segment stitched under one logical `run_id`); supported on CrewAI only at task/flow-checkpoint boundaries.

A `ApprovalCapability` declaration per adapter (`{inline: true, durable: "native" | "segmented" | false}`) plus honest docs is *more* impressive than a fake uniform API, and it's the kind of finding a maintainer would actually thank you for.

### FLAG 2 — AutoGen is in maintenance mode; building one of three pillar adapters on it is a dating risk

Confidence: **HIGH** (verified on the `microsoft/autogen` README)

The README states AutoGen "is now in maintenance mode. It will not receive new features or enhancements and is community managed going forward," recommends **Microsoft Agent Framework (MAF)** as "the enterprise-ready successor," links an official AutoGen → MAF migration guide, and restricts contributions to bug fixes, security patches, and docs. Active packages remain `autogen-agentchat` / `autogen-ext` / `autogenstudio`. Secondary sources (MEDIUM confidence) put maintenance mode at Oct 2025, MAF 1.0 (SK + AutoGen merger) at April 2026, and warn of API deprecations later in 2026 — treat the specific dates as unverified, but the direction is not in doubt.

**Implication for scope, not a reason to drop it:** keeping the AutoGen adapter is still defensible (large installed base, matches `prompt.md` exactly, and a control plane's whole pitch is governing frameworks you didn't choose). But:

- Pin `autogen-agentchat` to an exact version and say so in the README. Do not float.
- Add a short `docs/` note on the AutoGen → MAF trajectory and what it means for this adapter. Omitting this reads as stale research; including it reads as current.
- **Best-value move:** the strongest possible proof that the adapter interface is real is a *fourth* adapter — and MAF is the obvious candidate. `.planning/PROJECT.md` correctly puts a 4th adapter out of scope for v1; keep it out of scope, but make "add MAF adapter" the worked example in `docs/how-to-add-an-adapter.md`. Costs a doc, buys enormous credibility.

### FLAG 3 — The cross-framework benchmark, as scoped, will be attacked on methodology and is partly meaningless under the mandated mock-LLM path

Confidence: **MEDIUM-HIGH**

Two independent problems:

1. **The space is already saturated.** Multiple published comparisons already report the same headline: LangGraph lowest latency/tokens, CrewAI ~1.7–3x token overhead from "managerial" agent chatter, AutoGen above LangGraph because it resends full conversation history to all agents by design. A v1 benchmark that re-derives these numbers adds nothing, and a benchmark asserting "framework X wins" from a handful of runs on three bespoke workflows invites immediate methodology criticism (no fixed seed, n too small, different agent counts, different prompt budgets → not apples to apples).
2. **`.planning/PROJECT.md` requires demos to run without paid API keys via a mock/local LLM.** Under a mock LLM, *token usage and latency numbers are synthetic and carry no information.* You cannot publish them as benchmark results.

**Recommended reshape for v1** — retarget the benchmark at what this project uniquely can measure and what *is* valid under a mock LLM:

- **Control-plane overhead**: ms and % added by policy checks + tracing vs. an unwrapped run of the same graph/crew/conversation. This is the number a platform team actually asks for before adopting a governance layer, and nobody else publishes it.
- **Behavioural fingerprint per framework**, under an identical logical workflow and identical mock LLM: step count, LLM-call count, tool-call count, approvals triggered, policy denials triggered, retries. These are structural, deterministic under a mock, and genuinely interesting — they quantify CrewAI's overhead and AutoGen's history-resend as *step/call counts* rather than as dollar figures.
- **Optional keyed mode** (`--live`) that fills in real token/cost/latency when the operator supplies an API key, with n, model, temperature, and seed recorded in the output.

Frame the deliverable as "control-plane overhead + framework behaviour fingerprint," explicitly *not* "which framework is best." Publish the methodology (model, temperature, n, seed, workflow parity constraints) alongside the results table. This converts the weakest requirement into a defensible one.

---

## Feature Landscape

### Table Stakes (Platform Teams Expect These)

Missing any of these and a platform team files the project under "demo."

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Declarative policy file (YAML) with fixed, documented schema** | Every governance product in the space is policy-as-code. Non-declarative = not reviewable, not version-controllable. | LOW | Already in scope. Keep the schema *fixed-field*, not a DSL — see anti-features. |
| **Enforcement outside the agent's own code/prompt** | The entire value claim. Industry consensus is explicit: enforcement inside the agent prompt is bypassable by the agent; it must live in the governance plane. | MEDIUM | Already in scope. This is the line between EACP and "a system prompt that says please don't." |
| **Token/cost caps enforced at runtime (not declared)** | Hard requirement. Widely-cited failure mode: a multi-agent loop billed ~$47k over 11 days with no cap. LiteLLM/Portkey both enforce per-key budgets in OSS. | MEDIUM | Already in scope. **Needs a pinned model→$/token pricing table + an "unknown model ⇒ token-only enforcement" fallback**, which is not currently in scope and silently breaks `max_cost_per_day`. |
| **Persistent, atomic daily/periodic budget counter** | `max_cost_per_day` is cross-run, cross-process state. In-memory means the flagship feature dies on restart. | MEDIUM | **Missing from scope.** Needs a SQLite counter keyed `(policy_id, tenant_id, day)` updated in one transaction. ~40 lines; without it the headline feature is theatre. |
| **Warn threshold + hard stop (e.g. 80% / 100%)** | Standard across every budget-guard product surveyed. A cap that only ever hard-fails is operationally hostile. | LOW | Cheap add on top of the counter. |
| **Tool allow/deny enforced at call time** | Table stakes for any gateway-class product; OPA/Rego gateways and MCP guardrails all gate tool invocation. | MEDIUM | Already in scope. Cost is per-adapter interception, not the policy logic. |
| **Structured, explainable denials** | A boolean `False` is unusable in production. Operators need: which policy, which version, which rule, the limit, the observed value. | LOW | **Missing from scope.** Return a `Decision` object, not a bool. Cheap, and it's what makes traces worth reading. |
| **Per-run trace: per-node / per-agent, with latency + tokens + tool outcomes** | Universal. Langfuse/Phoenix/Braintrust/Datadog all model this as trace→spans with timing, tokens, cost per span. | MEDIUM | Already in scope. **Emit OpenTelemetry GenAI semconv, don't invent a schema** — see differentiators. |
| **Run history store with queryable run metadata + status** | Cannot debug or audit without it. | LOW | Already in scope (SQLite, pluggable). |
| **Policy decision audit log, separate from the run trace** | EU AI Act Art. 12 requires automatic event recording over system lifetime; Art. 19 / 26(6) require ≥6 months retention; Annex III obligations reported as effective 2026-08-02. Guidance converges on per-interaction fields: timestamp, operator ID, model version, input, output, **governance policy applied, and any policy flags triggered**. | LOW-MEDIUM | **Missing from scope.** A run trace is for debugging; an append-only decision log is the compliance artefact. For a project whose pitch word is "compliance-aware," this is the single most conspicuous gap. Append-only table, no deletes, policy version recorded per row. |
| **Policy versioning, pinned to each run** | You cannot reproduce or defend a past decision if the policy file has since changed. | LOW | **Missing from scope.** Store the policy content hash (and optional semver) on the run record and on every audit row. ~15 lines. |
| **Human approval before irreversible actions** | Table stakes for the enterprise positioning; LangGraph ships it as middleware, CrewAI as `human_input`, AutoGen as `UserProxyAgent`. | MEDIUM-HIGH | In scope — but **reshape per FLAG 1**. High complexity comes entirely from cross-framework durability semantics. |
| **CLI approve/deny/resume** | `prompt.md` explicitly permits "simple UI or CLI." A CLI is sufficient and correct here. | LOW | In scope. |
| **Runnable examples with sample inputs, no paid key required** | An OSS governance library that a reviewer cannot execute in 5 minutes doesn't get reviewed. | MEDIUM | In scope, and correctly identified as a constraint. |
| **Per-adapter optional dependency extras** (`pip install eacp[langgraph]`) | `langgraph`, `crewai`, and `autogen-agentchat` each pin their own `pydantic` / `openai` / `litellm` ranges. A single fat install that resolves today is very likely to conflict as any one of them moves — and an install that fails is a project nobody evaluates. | LOW | **Missing from scope.** Confidence MEDIUM (design inference from the three packages' dependency surfaces, not a verified resolver run) — but verify resolution early, it's cheap to design for and expensive to retrofit. Core package must import zero framework SDKs. |
| **Docs: quickstart, policy reference, adapter-authoring guide** | Already in scope and correctly so. | MEDIUM | The adapter-authoring guide is load-bearing for the "not just a wrapper" claim. |

### Differentiators (Genuine Competitive Advantage)

Ordered by credibility-per-hour. The first three are, per this research, where the project actually wins.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **One policy file, three engines, enforced identically — with a conformance test suite proving it** | This is the Core Value, and research found **no existing OSS project spanning LangGraph + CrewAI + AutoGen with a real policy layer**. Vendor control planes are single-framework (CrewAI AMP, LangGraph Platform) or protocol-level (agentgateway governs MCP/A2A traffic, not in-framework node execution). The whitespace is real. | HIGH | The proof is not the adapters — it's a **shared conformance suite** run against all three adapters asserting the same policy produces the same allow/deny outcomes. That single test file is the most persuasive artefact in the repo. |
| **Policy dry-run / shadow mode (`enforce` \| `warn` \| `off`, per rule)** | Universal in mature policy-as-code (GCP Org Policy dry-run, Binary Authorization dry-run, Istio authz dry-run, OPA gateway shadow mode). The consistent lesson: controls promoted to blocking too fast lock out legitimate traffic, so teams need a report of "what *would* have been blocked" first. **No platform team turns on blocking without this.** | LOW | Requires the audit log (shadow verdicts must be recorded somewhere). Highest credibility-per-line-of-code item in this document. |
| **OpenTelemetry GenAI semantic conventions as the native trace format** | Instrument once, integrate with everything. Langfuse, Arize Phoenix, OpenLLMetry, Laminar, Datadog, Honeycomb, New Relic all consume `gen_ai.*`; the conventions define `create_agent`, `invoke_agent`, `invoke_workflow`, `execute_tool`, `chat`, `embeddings` — a near-perfect fit for a control plane's span model. Also removes any need to build a trace viewer. | MEDIUM | **Caveat (HIGH confidence):** the GenAI conventions are still marked *Development*, and reportedly moved to a dedicated `semantic-conventions-genai` repo as of v1.42.0 (2026-06-12). So **pin and document the spec version you target** and keep a thin mapping layer. Note LangChain/CrewAI/AutoGen already emit OTel spans natively or via instrumentation — nesting control-plane spans as parents of those is the whole win. |
| **Control-plane overhead benchmark** (ms and % added vs. unwrapped run) | The first question a platform team asks a governance layer is "what does this cost me." Nobody in the surveyed landscape publishes it. Valid under a mock LLM, unlike token/cost numbers. | MEDIUM | See FLAG 3. This is the benchmark that should lead the README. |
| **Adapter interface with a fourth adapter written as a documented exercise (MAF)** | Distinguishes "extensible by design" from "extensible in the README." Also neutralises FLAG 2 by showing awareness of where AutoGen is heading. | LOW (as a doc) | Do **not** ship a 4th adapter in v1. Write the guide against MAF as the worked target. |
| **`DECISION_FRAMEWORK.md` grounded in your own measured behavioural fingerprints** | A "when to use LangGraph vs CrewAI vs AutoGen" doc is commodity content — unless every claim cites a number your own benchmark produced. Then it becomes the canonical reference and is the highest-traffic page in the repo. | LOW (given the benchmark) | Depends on the benchmark runner. The step/call-count fingerprints make this doc credible without any paid API key. |
| **Per-tenant policy scoping with documented resolution order** | `prompt.md` explicitly asks for "per-tenant and per-workflow policies"; `.planning/PROJECT.md` silently dropped the tenant dimension. Per-tenant policy is the difference between a library and a platform primitive. | LOW | A `tenant_id` on run context + resolution order `tenant → workflow → default` is ~30 lines. **This is spec fidelity lost by accident — restore it.** It is *not* multi-tenancy infrastructure (which stays out of scope). |
| **Compliance tags that actually do something** | Currently scoped as labels only. A tag that only decorates is the exact "governance theatre" criticism the project is positioned against. | LOW | Make tags gate: e.g. a `PII`-tagged workflow may only use tools on the PII allowlist, and every tag propagates onto the audit record. Small change, removes a soft spot reviewers will poke. |
| **Guardrail *hook interface*** (not guardrail implementations) | Lets the project sit in front of NeMo Guardrails / Guardrails AI / Presidio / Bedrock Guardrails without owning any detection logic. Enterprise expectation is PII redaction + injection detection at the gateway. | LOW (interface) | One `pre_llm` / `post_llm` hook + one reference implementation using a regex or Presidio. **Do not build detectors** — see anti-features. |

### Anti-Features (Commonly Requested, Scope Traps for a Solo OSS Project)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Hosted web approval UI / dashboard** | "Approvals need a UI"; every commercial control plane has one. | Frontend + auth + hosting + session state. Unbounded maintenance for a solo maintainer, and it's the part reviewers judge *least* on. `prompt.md` explicitly permits CLI. | CLI approve/deny + emit an `approval_required` event/webhook so others can build a UI. Already correctly out of scope — keep it there. |
| **Own auth / RBAC / agent identity system** | "Who approved this? Which agent is this?" Genuinely important questions. | Rolling your own identity is the classic solo-project sinkhole, and the space is already owned (Microsoft Entra Agent ID, Agent 365, AWS Agent Registry GA'd 2026-08-31, Foundry per-agent Entra identity). Cryptographically verifiable agent identity is a multi-quarter effort. | Accept an opaque `approver_id` / `principal` string from the caller, record it in the audit log, and document "bring your own IdP." Already out of scope — keep it. |
| **Building your own LLM gateway** (routing, fallback, caching, virtual keys, retries) | Cost/token enforcement needs a measurement point, and a gateway is the obvious one. | This is LiteLLM's and Portkey's entire product; LiteLLM already ships virtual keys, per-key TPM/RPM, and budgets in OSS. Competing means losing. | Intercept at the **framework callback/hook layer** for enforcement, and document LiteLLM as the recommended upstream for provider routing + as an alternative token-accounting source. Composition, not competition. |
| **Own PII detectors / prompt-injection classifiers** | Enterprise guardrail checklists demand them. | ML detection work with an endless false-positive tail, entirely orthogonal to the control-plane thesis, and impossible to keep competitive solo. | Ship the hook interface (see differentiators) and one trivial regex reference impl. Adapt, don't author. |
| **Own tracing backend + trace viewer UI** | "I need to see my traces." | You'd be rebuilding Langfuse (Postgres + ClickHouse + Redis) badly. | Emit OTel GenAI spans; point users at Langfuse/Phoenix/Datadog. Keep SQLite strictly for run metadata + audit, not analytics. |
| **A general-purpose policy DSL (Rego/Cedar-grade), or an OPA sidecar dependency** | "Fixed YAML fields aren't expressive enough." | An expressive policy language is a language project. An OPA sidecar makes `pip install && python example.py` impossible, which kills the 5-minute reviewer path. | Keep the fixed-field YAML schema; add one `custom_check: module:function` escape hatch for callers who need arbitrary logic. Note OPA as a future integration in docs. |
| **Supporting every framework** (Agno, OpenAI Agents SDK, Google ADK, Semantic Kernel, PydanticAI, LlamaIndex…) | Breadth looks like ambition. | N adapters × per-framework hook/callback drift = N maintenance burdens on one person, and each new framework dilutes the conformance guarantee. Three is already a lot given FLAG 1. | Three adapters + an excellent authoring guide. Already out of scope — keep it, and resist it hard. |
| **Evals / datasets / LLM-as-judge / prompt management** | `prompt.md` says "evaluation hooks"; `observability + evaluation` is a common bundle. | This is Langfuse/Braintrust/Phoenix territory and a whole second product. Scope creep disguised as a checkbox. | Interpret "evaluation hooks" narrowly: the benchmark runner + a per-workflow `success_check` callable. Nothing more. |
| **Postgres / ClickHouse / cloud backends in v1** | "SQLite isn't production." | Real, but premature. Infra to stand up, test, and CI for a reference implementation with no users yet. | SQLite + a genuinely narrow store interface (≤6 methods). Already out of scope — keep it. |
| **A "which framework wins" verdict benchmark** | It's the most clickable artefact you could publish. | Invites methodology attacks you cannot win at n=3 workflows, and actively antagonises two of the three maintainer communities you're courting. Also invalid under the mandated mock-LLM path. | Overhead benchmark + neutral behavioural fingerprints, methodology published. See FLAG 3. |
| **Prometheus exporter / real-time metrics endpoint in v1** | `prompt.md` mentions "Prometheus-style." | A scrape endpoint implies a long-lived process; the v1 UX is CLI invocations. Wrong shape. | OTel metrics (which any Prometheus setup can already ingest via the collector) + JSON output. Free via the OTel decision. |
| **Cross-framework state/memory portability** ("run the same workflow definition on any backend from one spec") | It's the seductive reading of "unified workflow abstraction." | LangGraph state machines, CrewAI role hierarchies, and AutoGen conversation loops are not isomorphic. Forcing one spec to compile to all three yields the lowest-common-denominator abstraction that strips what makes each framework good — the documented failure mode of multi-provider abstraction layers. | Unify the **governance plane** (policy, approval, trace, audit, run metadata), not the **authoring model**. Each workflow is still written idiomatically in its native framework and *registered* with EACP. This distinction is the project's thesis — state it explicitly in the README, because reviewers will assume the wrong one. |

---

## Feature Dependencies

```
[Policy schema (YAML)]
    └──requires──> nothing (start here)

[Policy engine returning structured Decision]
    └──requires──> [Policy schema]
    └──requires──> [Policy versioning / content hash]

[Explainable denial]
    └──requires──> [Policy engine returning structured Decision]

[Dry-run / shadow mode]
    └──requires──> [Policy engine returning structured Decision]
    └──requires──> [Policy decision audit log]

[Policy decision audit log]
    └──requires──> [Run store (SQLite)]
    └──requires──> [Policy versioning / content hash]

[Token/cost enforcement]
    └──requires──> [Per-adapter LLM-call interception]
    └──requires──> [Model pricing table + unknown-model fallback]
    └──requires──> [Persistent atomic budget counter]  <-- requires [Run store]

[Tool allow/deny enforcement]
    └──requires──> [Per-adapter tool-call interception]

[Approval gate — inline mode]
    └──requires──> [Per-adapter HITL hook]
    └──requires──> [CLI approve/deny]

[Approval gate — durable mode]
    └──requires──> [Run store]
    └──requires──> [Per-adapter checkpointer/state persistence]
    └──requires──> [ApprovalCapability declaration per adapter]

[OTel GenAI span emission]
    └──requires──> [Per-adapter node/agent hooks]
    └──enhances──> everything observability-related

[Benchmark runner]
    └──requires──> [Run store] + [metrics] + [mock LLM determinism]
    └──requires──> [an unwrapped-run baseline path]   <-- for overhead measurement

[DECISION_FRAMEWORK.md with real numbers]
    └──requires──> [Benchmark runner]

[Per-tenant policy scoping]
    └──requires──> [Policy engine] + tenant_id on run context

[Conformance test suite]
    └──requires──> all three adapters + [Policy engine]

[Guardrail hook interface]
    └──requires──> [Per-adapter LLM-call interception]  (same seam as cost enforcement)

CONFLICTS
[Mock LLM path] ──conflicts──> [Token/cost/latency benchmark numbers]
[AutoGen blocking UserProxyAgent] ──conflicts──> [Durable suspend/resume approval]
[Single fat install of all 3 frameworks] ──conflicts──> [Reliable `pip install`]
[Unified authoring model] ──conflicts──> [Idiomatic per-framework workflows]
```

### Dependency Notes

- **Per-adapter interception is the real critical path.** Cost enforcement, tool restriction, tracing, and guardrail hooks all converge on one question per framework: *where can I intercept an LLM call and a tool call?* Solve that seam **once per adapter, first**, and four features fall out. Get it wrong and four features need rework. This should drive phase ordering more than anything else in this document.
- **Dry-run requires the audit log, not the other way round.** Shadow verdicts that aren't recorded are worthless. Build audit log → then dry-run.
- **Policy versioning is upstream of both audit and reproducibility.** Add the content hash on day one; retrofitting it means rewriting every audit row's provenance.
- **Benchmark needs an unwrapped baseline path.** Measuring control-plane overhead requires the ability to run each example *without* EACP wrapping. Design the adapter so `enforce: off` yields a genuinely bypassed path, not a no-op-check path — otherwise the overhead number is unmeasurable.
- **Mock LLM conflicts with token metrics.** Resolve by scope, not engineering: mock mode reports structural metrics only and says so in the output header; `--live` mode reports token/cost/latency with model + temperature + seed + n recorded.
- **Durable approval conflicts with AutoGen.** Resolve by capability declaration (FLAG 1), not by forcing it.

---

## MVP Definition

### Launch With (v1)

Ruthless cut. Everything here is either the thesis or a credibility gate.

- [ ] **Policy schema (YAML) + loader** — the thesis starts here
- [ ] **Policy engine returning a structured `Decision`** (allow/deny + policy id + version + rule + limit + observed) — a bool is unusable
- [ ] **Policy versioning via content hash, pinned to every run and audit row** — no reproducibility without it
- [ ] **Workflow registry + execution router** — in scope, straightforward
- [ ] **Per-adapter interception seam** (LLM call + tool call + node/agent boundary) — the critical path; all enforcement rides on it
- [ ] **Tool allow/deny enforcement** — cheapest credible "actually enforced" proof
- [ ] **Token/cost enforcement** incl. pricing table, unknown-model fallback, persistent atomic budget counter, 80% warn / 100% stop — the headline feature, and it is not done without the counter
- [ ] **Dry-run / shadow mode per rule (`enforce` | `warn` | `off`)** — LOW cost, and without it no platform team enables blocking
- [ ] **Policy decision audit log** (append-only; timestamp, run, workflow, tenant, policy id + version, rule, verdict, principal, compliance tags) — the compliance artefact the positioning promises; EU AI Act Art. 12 shape
- [ ] **Run store (SQLite) + run metadata** — in scope
- [ ] **Approval gate, `inline` mode, on all three backends** + CLI approve/deny — this alone satisfies `prompt.md`
- [ ] **Approval gate, `durable` mode, LangGraph only**, with `ApprovalCapability` declared per adapter and the limitation documented — honest beats uniform
- [ ] **OTel GenAI semconv span emission** (pinned spec version) — trace format decision, not a feature to defer
- [ ] **Three adapters** (LangGraph, CrewAI, `autogen-agentchat` pinned) with **optional dependency extras**
- [ ] **Three examples** (contract review / sales intel / incident response) runnable under mock LLM, one CLI entrypoint each
- [ ] **Conformance test suite**: same policy → same allow/deny outcomes across all three adapters — the single most persuasive file in the repo
- [ ] **Per-tenant policy scoping** with documented resolution order — restores lost `prompt.md` fidelity for ~30 lines
- [ ] **Compliance tags that gate something** — removes the "governance theatre" attack surface
- [ ] **Benchmark runner**: control-plane overhead + behavioural fingerprint (mock mode), `--live` optional, methodology published
- [ ] **Docs**: README, DECISION_FRAMEWORK.md (citing own numbers), 3 tutorials, policy reference, adapter-authoring guide targeting MAF, AutoGen→MAF status note
- [ ] **PR description text**

### Add After Validation (v1.x)

- [ ] **`durable` approval on AutoGen** via terminate → `save_state()` → resume-as-segment, stitched under one logical `run_id` — trigger: someone asks for it, or inline mode proves insufficient in a real deployment. Genuinely hard; do not let it block v1.
- [ ] **`durable` approval on CrewAI** via `Flow` checkpoints — trigger: same. Verify CrewAI's checkpointing API has stabilised first.
- [ ] **Guardrail hook interface + Presidio/NeMo reference adapter** — trigger: first PII-handling user.
- [ ] **Webhook / event emission on `approval_required`** — trigger: someone wants to build a UI. This is how you get a UI *without building one*.
- [ ] **MAF adapter** — trigger: MAF API stability is credible, or a user asks. The authoring guide should already make this a small PR.
- [ ] **Policy `custom_check: module:function` escape hatch** — trigger: first "YAML isn't expressive enough" issue.
- [ ] **Prometheus/OTel metrics export for long-lived processes** — trigger: first server-mode deployment.

### Future Consideration (v2+)

- [ ] **Postgres / ClickHouse store backends** — defer: no users, no scale pressure, real CI cost.
- [ ] **Web approval UI** — defer: better as a separate repo consuming the webhook. Keeps this repo's maintenance bounded.
- [ ] **OPA/Rego or Cedar integration** — defer: contradicts the zero-sidecar install story that makes the project reviewable in 5 minutes.
- [ ] **Agent identity / cryptographic attestation** — defer: owned by Entra Agent ID, AWS Agent Registry, Foundry. Integrate later; never build.
- [ ] **Evals, datasets, LLM-as-judge** — defer: a second product.
- [ ] **A2A / MCP-level governance** — defer: this is agentgateway's (Linux Foundation) layer, and it's complementary, not competing. Worth a "how EACP relates to agentgateway" doc section in v1 though; reviewers *will* ask.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Per-adapter interception seam | HIGH | MEDIUM | **P1** (critical path — do first) |
| Policy schema + engine returning `Decision` | HIGH | LOW | **P1** |
| Token/cost enforcement + persistent atomic counter + pricing table | HIGH | MEDIUM | **P1** |
| Tool allow/deny enforcement | HIGH | MEDIUM | **P1** |
| Policy decision audit log | HIGH | LOW | **P1** |
| Policy versioning (content hash pinned to run) | MEDIUM | LOW | **P1** |
| Dry-run / shadow mode | HIGH | LOW | **P1** (best value in the document) |
| Explainable denials | HIGH | LOW | **P1** |
| Approval gate — `inline`, all three backends | HIGH | MEDIUM | **P1** |
| Approval gate — `durable`, LangGraph + capability declaration | HIGH | MEDIUM | **P1** |
| OTel GenAI semconv emission | HIGH | MEDIUM | **P1** |
| Conformance suite across three adapters | HIGH | LOW-MEDIUM | **P1** |
| Optional dependency extras per adapter | HIGH | LOW | **P1** (install failure = zero evaluations) |
| Three runnable examples under mock LLM | HIGH | MEDIUM | **P1** |
| Overhead + fingerprint benchmark | HIGH | MEDIUM | **P1** |
| Per-tenant policy scoping | MEDIUM | LOW | **P1** (spec fidelity, trivial) |
| Compliance tags that gate | MEDIUM | LOW | **P1** |
| Adapter-authoring guide targeting MAF | MEDIUM | LOW | **P1** |
| DECISION_FRAMEWORK.md citing own numbers | HIGH | LOW | **P1** (given benchmark) |
| Warn threshold (80%) | MEDIUM | LOW | P2 |
| `durable` approval on AutoGen / CrewAI | MEDIUM | HIGH | P2 |
| Guardrail hook interface | MEDIUM | LOW | P2 |
| `approval_required` webhook | MEDIUM | LOW | P2 |
| Live-mode token/cost benchmark | MEDIUM | LOW | P2 |
| Policy `custom_check` escape hatch | LOW | LOW | P2 |
| MAF adapter | MEDIUM | MEDIUM | P3 |
| Postgres backend | LOW | MEDIUM | P3 |
| Web approval UI | MEDIUM | HIGH | P3 (separate repo) |
| OPA/Rego integration | LOW | HIGH | P3 |
| Agent identity | LOW (for this project) | HIGH | P3 (never build) |
| Evals / datasets / judges | LOW | HIGH | P3 |

**Priority key:** P1 = must have for launch · P2 = should have, add when possible · P3 = future consideration

---

## Competitor Feature Analysis

| Feature | LangGraph Platform / LangSmith | CrewAI AMP | AI gateways (LiteLLM / Portkey) | Microsoft Agent 365 / AWS AgentCore / Gemini Enterprise | agentgateway (Linux Foundation) | **EACP (our approach)** |
|---|---|---|---|---|---|---|
| **Framework coverage** | LangGraph only | CrewAI only | Framework-agnostic but **LLM-call level only** — no knowledge of nodes/roles/turns | Own runtime / own agent model | Any framework speaking MCP or A2A — **protocol level, not in-framework** | **Three frameworks, at the node/role/turn level.** The uncontested gap. |
| **Policy enforcement** | Platform-level config; no cross-framework policy artefact | Enterprise-wide policies within CrewAI AMP | Per-virtual-key budgets, TPM/RPM, content guardrails; OPA/Rego available in some (TrueFoundry) | Guardrails + gateway-mediated policy (Bedrock Guardrails, Model Armor) | Gateway policy on agent↔tool / agent↔LLM / agent↔agent traffic | **One YAML file, enforced identically across all three engines, proven by a conformance suite** |
| **Cost / token limits** | Usage-based platform metering | LLM consumption view in the Agent Control Plane | Strongest in class: virtual keys, per-key budgets, auto-block on breach | Native per-service quotas | Traffic-level limits | Per-policy + per-tenant caps enforced at node level, persisted, warn + hard stop. Integrates with LiteLLM rather than competing. |
| **Tracing** | LangSmith (first-party, deep) | AMP tracing (batched, first-party) | Request/response logs | Cloud-native observability | OTel-native traffic telemetry | **OTel GenAI semconv, so any of Langfuse/Phoenix/Datadog renders it.** No viewer built. |
| **Human-in-the-loop** | Best in class: native `interrupt()` + checkpointer, approve/edit/reject/respond | Task-level `human_input` | None (wrong layer) | Varies | None (wrong layer) | Unified **API** with honest **per-backend capability declaration** — inline everywhere, durable where the framework permits |
| **Audit / compliance log** | Platform audit | Governance + auditability (enterprise tier) | Request logs | Strong (enterprise identity + compliance) | Traffic audit | **Append-only policy-decision log shaped to EU AI Act Art. 12 fields, policy-version-pinned** |
| **Dry-run / shadow mode** | Not surfaced | Not surfaced | Available in some OPA-backed gateways | Varies by product | Not surfaced | **First-class, per-rule `enforce`/`warn`/`off`** |
| **Cross-framework benchmark** | No (single framework) | No | No | No | No | **Control-plane overhead + neutral behavioural fingerprints, methodology published** |
| **Deployment model** | SaaS / hybrid / self-host, Postgres + Redis required | SaaS control plane | Self-host or SaaS | Cloud-only | Self-host proxy | **`pip install`, SQLite, no sidecar, no server.** The 5-minute reviewer path is a feature. |
| **Licensing / lock-in** | Commercial platform | Commercial | LiteLLM OSS core / Portkey hybrid | Cloud lock-in | Apache, LF-neutral | OSS reference implementation, vendor-neutral by construction |

**Positioning conclusion:** the landscape splits into single-framework vendor control planes (deep, locked-in) and protocol/LLM-level gateways (broad, framework-blind). Nothing surveyed governs *inside* multiple agent frameworks with one policy artefact. That is a genuinely defensible niche — **provided** the project ships the conformance suite that proves the "identically" claim, and is honest about FLAG 1 rather than faking uniformity.

---

## Summary of Changes Recommended to `.planning/PROJECT.md`

**Reshape (currently unrealistic as written):**
1. Approval gate → two declared modes (`inline` all backends / `durable` LangGraph-native, others v1.x) + `ApprovalCapability` per adapter. *(FLAG 1, HIGH confidence)*
2. Benchmark runner → control-plane overhead + behavioural fingerprint under mock LLM; token/cost/latency moves to an optional `--live` mode with published methodology. *(FLAG 3)*
3. AutoGen adapter → keep, but pin `autogen-agentchat` exactly and add a maintenance-mode / MAF-successor note to docs. *(FLAG 2, HIGH confidence)*
4. `compliance_tags` → must gate something, not just label.

**Add (commonly expected, currently missing):**
5. Policy decision audit log, append-only, EU AI Act Art. 12 field shape — LOW cost, highest credibility gap
6. Policy versioning via content hash, pinned to run and audit rows — LOW cost, upstream of reproducibility
7. Dry-run / shadow mode per rule — LOW cost, gates real adoption
8. Structured explainable denials (`Decision` object, not bool) — LOW cost
9. Persistent atomic budget counter + model pricing table + unknown-model fallback — without these `max_cost_per_day` does not work
10. OTel GenAI semconv as the trace format (pinned spec version) — replaces bespoke JSON schema
11. Per-tenant policy scoping — restores `prompt.md` fidelity, ~30 lines
12. Optional per-adapter dependency extras; core imports zero framework SDKs — install reliability
13. Cross-adapter conformance test suite — the proof of the Core Value claim
14. README section on how EACP relates to agentgateway / AI gateways / vendor control planes — reviewers will ask

**Confirm as out of scope (research agrees strongly):** hosted UI, own auth/identity, own gateway, own PII/injection detectors, own trace viewer, policy DSL/OPA sidecar, 4th adapter, Postgres, evals/datasets/judges, unified *authoring* model.

---

## Sources

**HIGH confidence (official docs / primary):**
- AutoGen repository README — maintenance mode, MAF successor, contribution restrictions, active packages: https://github.com/microsoft/autogen
- AutoGen Human-in-the-Loop docs — `UserProxyAgent` blocking, "unstable state that cannot be saved or resumed," terminate→save_state→resume pattern: https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/human-in-the-loop.html
- AutoGen Managing State docs — `save_state()` / `load_state()`: https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/state.html
- LangChain human-in-the-loop docs — interrupt middleware, approve/edit/reject/respond, checkpointer requirement: https://docs.langchain.com/oss/python/langchain/human-in-the-loop
- LangGraph Control Plane concepts: https://langchain-ai.github.io/langgraph/concepts/langgraph_control_plane/
- LangSmith data plane docs — Postgres/Redis architecture: https://docs.langchain.com/langgraph-platform/data-plane
- CrewAI checkpointing docs: https://docs.crewai.com/v1.15.17/en/concepts/checkpointing
- CrewAI tracing docs: https://docs.crewai.com/en/observability/tracing
- Langfuse docs — OSS observability feature set, self-host stack: https://langfuse.com/docs
- Amazon Bedrock Guardrails — six safeguard policies: https://aws.amazon.com/bedrock/guardrails/
- Linux Foundation press release, agentgateway — vendor-neutral governance, MCP/A2A scope: https://www.linuxfoundation.org/press/linux-foundation-welcomes-agentgateway-project-to-accelerate-ai-agent-adoption-while-maintaining-security-observability-and-governance
- agentgateway docs: https://agentgateway.dev/docs/standalone/latest/documentation/about/introduction/
- Microsoft Agent 365 — control-plane framing, five capabilities: https://www.microsoft.com/en-us/microsoft-365/blog/2025/11/18/microsoft-agent-365-the-control-plane-for-ai-agents/
- GCP Org Policy dry-run mode — canonical staged-enforcement pattern: https://docs.cloud.google.com/binary-authorization/docs/enabling-dry-run

**MEDIUM confidence (multiple secondary sources agreeing, or vendor marketing):**
- OpenTelemetry GenAI semantic conventions status, operation names, dedicated repo move at v1.42.0 (2026-06-12), "Development" stability — corroborated across Greptime, Dash0, MLflow, Datadog: https://greptime.com/blogs/2026-05-09-opentelemetry-genai-semantic-conventions · https://www.dash0.com/knowledge/opentelemetry-genai-semantic-conventions-explained · https://mlflow.org/docs/latest/genai/tracing/opentelemetry/genai-semconv/ · https://www.datadoghq.com/blog/llm-otel-semantic-convention/
- EU AI Act Art. 12 logging / Art. 19 + 26(6) ≥6-month retention / Annex III 2026-08-02 / required log fields — corroborated across Help Net Security, Prediction Guard, Kognitos: https://www.helpnetsecurity.com/2026/04/16/eu-ai-act-logging-requirements/ · https://predictionguard.com/blog/eu-ai-act-compliance-audit-log-what-regulators-expect-and-how-to-document-it · https://www.kognitos.com/blog/ai-audit-trail-requirements-2026-checklist/
- AI gateway feature baselines (virtual keys, per-key budgets, TPM/RPM, guardrails): https://api7.ai/portkey-vs-litellm · https://www.almtoolbox.com/blog/litellm-ai-gateway-cost-tracking-guardrails-budgets/ · https://portkey.ai/buyers-guide/leading-llm-gateway-platforms
- CrewAI AMP / Agent Control Plane feature set: https://deepwiki.com/crewAIInc/crewAI/6-observability-and-monitoring
- Runaway-cost failure mode, circuit breakers, kill switches, warn-at-80% pattern, the cited ~$47k incident: https://www.getreadyforagents.com/blog/agent-cost-runaway-detection-token-enforcement-production/ · https://www.waxell.ai/blog/ai-agent-circuit-breaker-pattern · https://auxot.com/blog/agent-cost-circuit-breakers
- Cross-framework benchmark numbers (CrewAI ~4120 vs LangGraph ~2350 median tokens/task; AutoGen resends full history): https://dev.to/priyeshdave6/why-langgraph-wins-benchmarking-langgraph-crewai-and-autogen-on-107-real-data-engineering-tasks-3ljg · https://markaicode.com/benchmarks/langchain-vs-crewai-benchmark/ — *treat specific figures as indicative only; methodologies differ and are not independently reproduced*
- Lowest-common-denominator / leaky abstraction critique of multi-provider layers: https://tianpan.co/blog/2026/07/02/the-abstraction-layer-that-made-every-model-mediocre
- Control-plane capability taxonomies (registry, identity, runtime policy, observability): https://www.speakeasy.com/resources/ai-control-plane · https://drata.com/learn/agent-gov/agentic-control-plane
- Agent registry landscape (AWS Agent Registry GA 2026-08-31, Bedrock AgentCore GA 2025-10-13, Foundry per-agent Entra identity): https://www.exploreagentic.ai/agent-registry/ · https://aws.amazon.com/blogs/machine-learning/manage-agents-tools-and-skills-at-scale-with-aws-agent-registry/
- OPA/Rego for agent + MCP tool authorization, layered enforcement: https://www.truefoundry.com/docs/ai-gateway/opa-guardrails · https://developers.redhat.com/articles/2025/12/12/advanced-authentication-authorization-mcp-gateway
- Gateway-layer guardrails as enterprise baseline (PII redaction, injection detection pre-LLM): https://www.getmaxim.ai/articles/enterprise-ai-guardrails-for-pii-injection-and-toxicity/ · https://www.arthur.ai/column/redact-pii-before-external-llm-provider

**LOW confidence (single source, unverified — flagged inline, not relied upon for recommendations):**
- Specific AutoGen/MAF dates: maintenance mode Oct 2025, MAF 1.0 on 2026-04-03, "Q3 2026 API deprecations": https://aidevdayindia.org/blogs/ai-agent-framework-decision-matrix/is-autogen-deprecated-maintenance-mode-microsoft.html · https://alexbevi.com/blog/2026/06/18/two-lineages-one-framework-how-autogen-and-semantic-kernel-became-the-microsoft-agent-framework/ — the *direction* is HIGH (confirmed on the repo README); the *dates* are not verified
- CrewAI flow-level pause/resume limitation: single community thread — https://community.crewai.com/t/how-do-you-pause-and-resume-flows/6376 — **verify directly against the installed CrewAI version before designing around it**
- Dependency-conflict risk across `langgraph` + `crewai` + `autogen-agentchat` in one environment: design inference, not a verified resolver run — **verify empirically in the first phase**

---
*Feature research for: agent control plane / multi-framework agent governance*
*Researched: 2026-09-24*
