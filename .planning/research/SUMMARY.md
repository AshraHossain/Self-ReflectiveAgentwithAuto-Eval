# Project Research Summary

**Project:** Enterprise Agent Control Plane (EACP)
**Domain:** Vendor-agnostic governance / control plane over Python multi-agent frameworks (LangGraph, CrewAI, AutoGen-lineage)
**Researched:** 2026-09-24
**Confidence:** HIGH on stack/packaging/framework hooks · MEDIUM on cross-framework HITL design (genuinely novel) · MEDIUM-HIGH on features/market

## Executive Summary

EACP is a governance layer, not a framework and not a SaaS. All four research tracks converge on the same thesis: **unify the control plane (policy, approval records, trace, audit, run history) and never unify the authoring model.** Workflows stay authored natively in LangGraph / CrewAI / ag2; `workflow.yaml` carries only identity + policy binding + an opaque entrypoint pointer. The moment the schema grows `nodes`/`agents`/`edges`, the project becomes a worse version of three frameworks (PITFALLS 8, ARCHITECTURE Anti-Pattern 1) — this is the highest-leverage, least-reversible decision in the project.

The recommended implementation shape is a **pure policy decision point (PDP) plus thin per-backend enforcement shims injected into each framework's own object graph** (custom model client + wrapped tool objects). Injection beats "adapter calls `policy.check()`" because a forgotten call is a silent policy bypass, whereas injection makes enforcement structurally verifiable in ~5 lines per adapter. All three frameworks expose real interception seams in 2026 — no monkey-patching: LangGraph node wrapping + `interrupt()`/`SqliteSaver`; `crewai.hooks` (`before_tool_call` / `before_llm_call`, `HookAborted`); ag2 `BaseMiddleware.on_tool_execution` + `observers` + `hitl_hook`.

Two hard truths must be shipped as features rather than hidden. **First, the "AutoGen" name maps to four different PyPI packages with different import roots and maintenance states; the correct target is `ag2>=1.1,<2` (imports as `ag2`, 14 transitive deps, released 2026-09-24), and the adapter module must be named for the package, not the brand.** Second, **uniformly durable pause/resume is not achievable across these three frameworks** — LangGraph is DURABLE, ag2/AutoGen is SNAPSHOT (message-boundary), CrewAI is BLOCKING/SEGMENTED. Resolve by declaring `AdapterCapabilities` and failing loudly at registration when a policy needs a capability the adapter lacks. The unified artifact is the `ApprovalRequest` **row** in the store plus the CLI that reads it — never `input()`. Remaining top risks: post-hoc budget checks (a report, not a budget), token usage silently reading zero, prompt-level "tool restriction", LangGraph node replay double-counting cost, and a 155-package monolithic install that fails outright on Intel macOS.

## Key Findings

### Recommended Stack

Python 3.12 (CrewAI caps `<3.14`), `uv` + committed lockfile, pydantic for policy schema, stdlib `sqlite3` behind a `Protocol` for stores, typer CLI, OpenTelemetry GenAI semconv attribute naming. Core package depends on **zero** agent frameworks; each adapter is an optional extra with lazy imports. That constraint is not hygiene — it is the proof the abstraction isn't LangGraph-shaped, and it's checkable with one CI grep.

**Core technologies:**
- **ag2 `>=1.1,<2`** — AutoGen-lineage backend. Actively maintained; native `middleware=` / `observers=` / `hitl_hook=` seams (near-exact fit for EACP); 14 deps. Avoid `autogen-agentchat` (~1yr stale), `pyautogen` (dead shim). Fallback: `autogen==0.14.x` ("AG2 Classic") if `GroupChat` semantics are required.
- **langgraph `>=1.2,<1.3` + langchain-core `>=1.6,<2` + langgraph-checkpoint-sqlite `>=3.1`** — best HITL story; `interrupt()` + `Command(resume=)` requires a checkpointer, non-optional.
- **crewai `>=1.15,<2`** — first-class `crewai.hooks` package with `HookAborted` (block-capable). 134 of 156 total packages; extra-only, never core.
- **pydantic `>=2.11,<2.13`** — the `<2.13` cap is forced by `crewai-core`, not preference. `extra="forbid"` on policy models.
- **opentelemetry-sdk/api `>=1.42,<2`** — already a hard dep of `crewai-core`; use as wire format, keep own SQLite rows as storage.
- **Native fakes, not mocks** — `FakeMessagesListChatModel`, `ag2.testing.TestConfig`, a `BaseLLM` subclass. Three shims, not one.

Platform matrix is a real constraint: Linux x86_64/arm64 and macOS arm64 resolve; **macOS x86_64 fails hard** (no `lancedb` wheel). Document it.

### Expected Features

**Must have (table stakes):**
- Declarative YAML policy, fixed-field schema (no DSL), `yaml.safe_load` only
- Policy engine returning a structured `Decision` (policy id + version + rule + limit + observed), never a bool
- Policy versioning via content hash pinned to every run and audit row
- Pre-call token/cost admission + reconciliation + **persistent atomic daily counter** (SQLite, keyed by policy + UTC date) + `max_steps` ceiling
- Tool allow/deny enforced at invocation inside a wrapper, including across delegation edges
- Append-only policy-decision audit log (EU AI Act Art. 12 field shape), separate from the debug trace
- Approval gate as store rows + `eacp approve/deny` CLI; `inline` mode on all three backends, `durable` on LangGraph
- Per-run trace with per-node latency/tokens/tool outcomes; `usage_source: provider|estimated|MISSING`
- Per-adapter optional dependency extras; `import eacp` works with zero frameworks
- Three runnable keyless examples, three scenarios each (approve / deny / violation)

**Should have (competitive):**
- **Cross-adapter conformance suite** — same policy, same allow/deny on all three backends. The single most persuasive file in the repo; it turns the Core Value claim from assertion into proof.
- **Dry-run / shadow mode per rule (`enforce`|`warn`|`off`)** — highest credibility-per-line item; no platform team enables blocking without it.
- **Control-plane overhead benchmark** (ms and % vs. unwrapped run) + neutral behavioural fingerprints. Nobody publishes this, and it's the only benchmark valid under a mock LLM.
- `AdapterCapabilities` matrix, machine-readable, validated at registration
- Per-tenant policy scoping (`tenant → workflow → default`), ~30 lines of lost `prompt.md` fidelity
- Compliance tags that actually gate something (tool allowlists, trace redaction)
- Adapter-authoring guide written against Microsoft Agent Framework as the worked 4th-adapter target
- `DECISION_FRAMEWORK.md` citing only numbers this project measured, incl. "The AutoGen naming situation"

**Defer (v2+):**
- Durable approval on CrewAI/ag2 (segmented / terminate-save-resume) · guardrail hook interface + Presidio ref impl · `approval_required` webhook · MAF adapter · `custom_check` escape hatch · Prometheus endpoint · Postgres/ClickHouse · web approval UI (separate repo) · OPA/Rego · agent identity · evals/judges · unified authoring model (never)

### Architecture Approach

Pure PDP + injected PEPs, with run identity carried out-of-band via `contextvars` (framework hook signatures are fixed and cannot receive a `RunContext`). One CrewAI hook registered at import time dispatching on `current_run()`, no-op when unbound — this both isolates concurrent runs and avoids CrewAI's process-global hook accumulation. Framework imports live in exactly three files.

**Major components:**
1. **models.py** — one file: Policy, Workflow, RunRecord, ApprovalRequest, Decision, Span, AdapterCapabilities
2. **Registry** — YAML load/validate, workflow_id/policy_id resolution, entrypoint allowlist
3. **Router** — sole owner of `run_id`, pre-flight static validation, adapter dispatch, `resume()`
4. **PolicyEngine (PDP)** — pure `decide(PolicyContext) -> Decision`; no I/O, no clock, no framework imports; 100% covered
5. **BudgetLedger** — the stateful half; upsert on `(run_id, node_id, call_index)` so replay is idempotent
6. **ApprovalService** — request/resolve/wait; append-only audit; approval keyed by `(run_id, node_id, payload_hash)`
7. **Tracer/Metrics** — own spans in SQLite, `gen_ai.*` attribute naming, `policy_decision` and `approval` as first-class spans
8. **Adapters ×3** — wiring only; own all framework imports; declare `AdapterCapabilities`
9. **llm/mock.py** — a deliverable, not a fixture: scripted tool calls (incl. forbidden), non-zero usage, runaway mode
10. **Stores** — narrow `Protocol` each (Run/Span/Approval/Checkpoint), SQLite impl, WAL, batched span writes

### Critical Pitfalls

1. **Wrong/ambiguous "AutoGen" package** — four codebases behind one name. Pick `ag2==1.1.x`, pin exactly, name the module `ag2_adapter.py`, record rejected alternatives. Phase 1, blocking; expensive to reverse after docs/benchmark.
2. **Monolithic dependency environment** — extras + lazy imports + per-adapter CI jobs + lockfile on day 1. Otherwise: 155 packages, ONNX Runtime for a contract-review demo, unresolvable on Intel macOS, random red PRs from CrewAI's daily nightlies.
3. **Approval gate as `input()`** — the gate is a persisted row the control plane owns; the framework hook is only delivery. Verification: approve from a *second process* with the first pending. Recovery cost if wrong: HIGH (rewrite of all three adapters).
4. **Post-hoc budget enforcement** — a `finally`-block check is a report. Enforce pre-call (estimate, hard block), reconcile post-call with provider usage, plus an independent `max_steps` ceiling. Document the bounded one-call overshoot honestly.
5. **Token accounting silently reads zero** — `usage_metadata` is dropped depending on `stream_mode`; three frameworks, three surfaces. Carry `usage_source`, never coerce to 0, `assert tokens > 0` per adapter, mock must report plausible usage.
6. **Lowest-common-denominator schema** — `entrypoint` is an opaque pointer to native user code. No topology fields, ever. Recovery cost: effectively a restart.
7. **LangGraph node replay** — resume re-runs the node from the top. Interrupt-only gate nodes, side effects in the *next* node, upsert ledger, and a regression test asserting post-resume token/span counts equal a single pass.
8. **Prompt-level tool restriction** — wrap the callable; test by invoking the forbidden tool *directly*, bypassing the model; enforce on delegation edges against the run's policy.

## Implications for Roadmap

Two dependency facts dominate ordering. **(a) The per-adapter interception seam is the critical path** — cost enforcement, tool restriction, tracing, and guardrail hooks all reduce to "where do I intercept an LLM call and a tool call in this framework?" Solve it once per adapter and four features fall out. **(b) The approval gate's data contract and the pre-call admission hook must exist before any adapter**, or they become three-adapter retrofits. And the adapter interface must be *extracted* from two working, maximally different adapters — not designed up front.

### Phase 1: Stack decision, scaffold, packaging
**Rationale:** Pitfalls 1 and 2 are both blocking and both cheap now / painful later. The `ag2` vs `autogen` choice changes module names, examples, docs, extras, and positioning.
**Delivers:** `pyproject.toml` with core deps + four extras, committed `uv.lock`, lazy-import adapter registry, 4-job CI matrix (`core` gates every push), README platform matrix, `models.py` skeleton.
**Avoids:** PITFALLS 1, 2.
**Exit:** `pip install eacp && python -c "import eacp"` succeeds with zero frameworks installed.

### Phase 2: Core schema, registry, stores
**Rationale:** The schema decision (govern, don't define) is the least reversible in the project; everything downstream is written against it.
**Delivers:** Policy/Workflow/Decision/Span/ApprovalRequest models, `safe_load` + entrypoint allowlist registry, store Protocols + SQLite impl (WAL), policy content hashing, per-tenant resolution order.
**Avoids:** PITFALLS 8, 12.
**Exit:** no `nodes`/`agents`/`edges` field exists; malicious entrypoint rejected by test.

### Phase 3: PDP + BudgetLedger + mock LLM
**Rationale:** The PDP is pure and fully unit-testable on day one with zero frameworks — if the rules are wrong everything downstream enforces the wrong thing. The mock arrives earlier than instinct suggests because every later phase's tests depend on it.
**Delivers:** pure `decide()`, structured `Decision`, dry-run/shadow mode, pre-call admission + post-call reconciliation, persistent daily counter, `max_steps`, `usage_source` contract, three mock/fake shims with scripted tool calls and non-zero usage.
**Avoids:** PITFALLS 5, 6, 11.
**Exit:** over-budget run stops early asserted by LLM-call count; daily cap survives a fresh process.

### Phase 4: Approval service + audit log + CLI
**Rationale:** Must precede the adapters — the gate's data contract determines the adapter interface. Building it now also makes approvals testable with no framework present.
**Delivers:** `ApprovalRequest` rows keyed by `(run_id, node_id, payload_hash)`, append-only decision audit log (Art. 12 shape), `eacp approvals list / approve / deny` with payload + triggering rule + cost-so-far rendered, default deny.
**Avoids:** PITFALLS 3, 15.
**Exit:** approve from a second process while the first is pending.

### Phase 5: LangGraph adapter + tracer
**Rationale:** Richest native support, so it validates the hardest path (durable suspend → CLI approve → resume) with the framework doing the work. Also delivers the strongest demo.
**Delivers:** model-client shim, wrapped tools, interrupt-only gate node, `SqliteSaver` with `thread_id = run_id`, `resume_seq`, OTel-shaped spans with batched writes, trace redaction honouring compliance tags.
**Avoids:** PITFALLS 4, 7, 13, 14.
**Exit:** post-resume token/span counts equal a single pass; direct forbidden-tool call raises.

### Phase 6: CrewAI adapter
**Rationale:** **Second, not third.** CrewAI is the worst HITL case; hitting the no-checkpoint wall with only one other adapter written is what forces the capability-tier design into existence early. Build ag2 second and you design a durable-resume interface that CrewAI later invalidates.
**Delivers:** single import-time global hook dispatching on `current_run()`, `before_tool_call`/`before_llm_call` enforcement via `HookAborted`, event-bus tracing, `HumanInputProvider` routed to EACP's gate, thread hand-off contextvar propagation, `clear_all_global_hooks()` test fixture.
**Avoids:** ARCH Anti-Pattern 5; the CrewAI-executor-fork scope trap.

### Phase 7: Extract adapter interface, then ag2 adapter
**Rationale:** Extract from two working, maximally different implementations — two points define the line, the third tests it. If ag2 needs no interface change, the abstraction is real.
**Delivers:** `Adapter` Protocol + `AdapterCapabilities` + registration-time capability validation; ag2 adapter via `middleware`/`observers`/`hitl_hook`; conformance suite parametrized over all installed adapters.
**Exit:** a `durable_pause`-requiring policy fails loudly at registration on CrewAI.

### Phase 8: Three examples
**Delivers:** contract review (LangGraph), sales intel (CrewAI), incident response (ag2) — each with approve / deny / violation scenarios, keyless, asserted on artifacts (status, trace, ledger) not LLM prose.
**Avoids:** PITFALL 10.

### Phase 9: Benchmark runner
**Delivers:** control-plane overhead (ms, % vs. a genuinely bypassed path) + behavioural fingerprints; mock-default, N>=5, median + spread, `--live` opt-in with model/temp/seed recorded, limitations section naming the scaffold confound.
**Avoids:** PITFALL 9. Depends on 4 and 6 being fixed first.

### Phase 10: Docs
**Delivers:** README (keyless first command, extras + platform matrix, "how EACP relates to AI gateways / agentgateway", governance-not-sandbox disclaimer), `DECISION_FRAMEWORK.md` (capability matrix + AutoGen naming situation + own measured numbers), three tutorials, adapter-authoring guide targeting MAF, PR description.
**Avoids:** PITFALL 16.

### Phase Ordering Rationale

- Packaging and the ag2/autogen decision are Phase 1 because both are ~20 lines now and touch every file later.
- Pure-logic phases (schema → PDP → ledger) precede all framework work: they need zero frameworks, are fully testable, and define the interfaces adapters are written against.
- Approval + admission hook land **before** adapters. This is the explicit prevention for the two HIGH-recovery-cost pitfalls (3 and 5).
- Adapter order is LangGraph → CrewAI → *extract interface* → ag2. Best-supported first to validate the hard path; worst HITL case second to force capability tiers; interface extracted from two, proven by the third.
- Benchmark after adapters are stable and after the replay/usage-zero fixes — benchmarking a broken ledger publishes confidently wrong numbers.
- Docs last, because `DECISION_FRAMEWORK.md` is only credible if written from what actually hurt.

### Research Flags

Phases likely needing `--research-phase` during planning:
- **Phase 6 (CrewAI):** whether `request_human_input` is usable from async without blocking the loop; whether `after_llm_call` exposes token usage or the shim must compute it; whether CrewAI's SQLite checkpoint provider is usable for segmented resume. Needs a code spike, not more reading.
- **Phase 7 (ag2):** `ag2.network` multi-agent ergonomics is MEDIUM confidence — module layout confirmed, no working 3-agent conversation executed, API ~2 months old. Also: `ag2.network.policies` / `hub.audit` ship overlapping governance primitives EACP must compose with rather than duplicate. **Spike before committing to the adapter design.**
- **Phase 3 (mock LLM):** three distinct model interfaces; plausibly its own phase.
- **Phase 9 (benchmark):** methodology design is the hard part, not the code.

Standard patterns (skip research):
- **Phase 1–2** — packaging, pydantic, YAML, SQLite are all verified and well-trodden.
- **Phase 4** — store-backed approval rows + typer CLI; no unknowns.
- **Phase 5** — LangGraph interrupt/checkpointer path is HIGH confidence with the replay gotcha already documented.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versions, hook surfaces, import roots read from published wheels; 156-package resolution and the macOS x86_64 failure verified by real `uv pip compile` on three platforms |
| Features | MEDIUM-HIGH | Framework capability claims verified against official docs (HIGH); competitor/market feature claims from vendor pages and secondary analysis (MEDIUM) |
| Architecture | MEDIUM-HIGH | Extension points HIGH (Context7 + wheel introspection); PDP/PEP pattern HIGH (XACML/OPA); cross-framework HITL MEDIUM — no prior art found, this part is likely novel |
| Pitfalls | HIGH | Packaging/framework state empirically verified; abstraction and benchmarking pitfalls MEDIUM (multi-source synthesis + academic literature) |

**Overall confidence:** HIGH on what to build with; MEDIUM on the one genuinely novel part (uniform HITL), which is why it is designed as a declared capability rather than a promise.

### Gaps to Address

- **`ag2.network` 3-agent ergonomics unproven** — time-box a spike in Phase 7; documented fallback is `autogen==0.14.x` (AG2 Classic), same Python range, `[ollama]` extra, far more community material.
- **Cost-attribution mechanics per backend** — does CrewAI's `after_llm_call` context carry usage, or must the shim compute it? Code spike in Phase 6. Prefer a single-source ledger from the layer you control.
- **CrewAI checkpoint/restore semantics** — modules and events confirmed present, behaviour untested. Gates segmented durable approval (v1.x anyway).
- **Whether `build(model, tools)` entrypoint contract feels natural in all three** — resolve during Phase 7 interface extraction; if it feels forced for one framework, that's a capability declaration, not a fudge.
- **Whether `crewai` can install without `chromadb`/`lancedb`** — worth 30 minutes; a `crewai-core`-only path would cut the dependency graph dramatically.
- **OTel GenAI semconv is still "Development" stability** and moved repos at v1.42.0 — pin the spec version, keep a thin mapping layer.
- **ag2 1.x churn** (0.13.1 → 1.1.0 in four months) — pin exactly, expect breakage on minor bumps, scheduled upgrade cron rather than floating.

## Sources

### Primary (HIGH confidence)
- PyPI JSON API, fetched 2026-09-24 — all versions, release dates, `requires_python`, `requires_dist`, extras
- Published wheels inspected directly — `ag2-1.1.0` (no `ConversableAgent`/`register_hook`; top-level `ag2/`), `autogen-0.14.1`, `crewai-1.15.22` (`crewai.hooks`, `HookAborted`, `InterceptionPoint`, `BaseLLM`, `HumanInputProvider`), `langchain_core-1.6.5` (fake chat models)
- `uv pip compile` 0.12.19 — 156-package resolution, pydantic `<2.13` binding constraint, per-framework weights (ag2 14 / langgraph 42 / crewai 134), macOS x86_64 hard failure via `lancedb`
- Context7 `/websites/langchain_oss_python_langgraph` — `interrupt()`, `Command(resume=)`, `SqliteSaver`, `get_state_history`, `error_handler`, node replay on resume
- Context7 `/llmstxt/crewai_llms_txt` + `/websites/microsoft_github_io_autogen_stable` — execution hooks; `Team`/`ChatCompletionClient` ABCs, `save_state`/`dump_component`
- `github.com/microsoft/autogen` README — maintenance mode, MAF as successor; AutoGen HITL docs ("unstable state that cannot be saved or resumed")
- `github.com/ag2ai/ag2` releases — v1.0 namespace change, Classic relocated to `ag2ai/ag2-classic`, "not a drop-in upgrade"
- GCP Org Policy / Binary Authorization dry-run docs — canonical staged-enforcement pattern

### Secondary (MEDIUM confidence)
- OTel GenAI semconv status and operation names — Greptime, Dash0, MLflow, Datadog (corroborating)
- EU AI Act Art. 12 logging / Art. 19+26(6) retention / Annex III 2026-08-02 — Help Net Security, Prediction Guard, Kognitos
- AI gateway baselines (LiteLLM/Portkey virtual keys, per-key budgets, TPM/RPM); CrewAI AMP feature set; Microsoft Agent 365 control-plane framing; Linux Foundation agentgateway
- Runaway-cost failure modes, circuit-breaker / warn-at-80% patterns, the ~$47k incident
- `langchain-ai/langgraph` issues #8094, #4848, #5951, #3936 — `usage_metadata` dropped per `stream_mode`
- `crewAIInc/crewAI` #2051 — `human_input` is stdin-only
- Academic: scaffold confound in agent benchmarks; "Benchmarking Crimes"; token-budget overrun catalog; ~42% of developers hindered by nested abstractions

### Tertiary (LOW confidence — flagged, not relied upon)
- Specific AutoGen/MAF dates (maintenance mode Oct 2025, MAF 1.0 2026-04-03, Q3 2026 deprecations) — direction confirmed, dates unverified
- AG2 v1.0.0/1.1.0 release dates from release notes (year mangled; PyPI treated as authoritative)
- CrewAI flow-level pause/resume limitation — single community thread; verify against the installed version
- Cross-framework token-count comparisons (CrewAI ~1.7-3x LangGraph) — indicative only, methodologies differ

---
*Research completed: 2026-09-24*
*Ready for roadmap: yes*
