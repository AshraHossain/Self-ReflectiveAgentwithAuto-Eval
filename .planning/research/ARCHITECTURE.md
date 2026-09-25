# Architecture Research

**Domain:** Multi-framework agent control plane (governance/observability layer over LangGraph, CrewAI, AutoGen)
**Researched:** 2026-09-24
**Confidence:** HIGH on framework extension points (verified against Context7 docs + local introspection of installed `crewai` 1.9.3). MEDIUM on cross-framework HITL design (no strong prior art exists — this is the genuinely novel part). HIGH on the PDP/PEP pattern (mature, borrowed from XACML/OPA).

---

## The One-Paragraph Thesis

Do not build a neutral workflow DSL, and do not put policy logic in the adapters. Build **one pure policy decision engine** plus **thin per-backend enforcement shims that get injected into each framework's own object graph** — specifically into the model client and the tool objects, which are the only two seams that exist in all three frameworks. The adapter's job is *wiring*, not *deciding*. And accept up front that human-in-the-loop **cannot** be made uniformly durable across these three frameworks: LangGraph has real suspend-to-disk, AutoGen has message-boundary state snapshots, CrewAI has neither. Make that difference a declared capability and a headline benchmark finding rather than a hidden bug.

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  ENTRYPOINTS                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐           │
│  │ eacp run     │  │ eacp approve │  │ benchmark runner  │           │
│  │ eacp trace   │  │ eacp deny    │  │                   │           │
│  └──────┬───────┘  └──────┬───────┘  └────────┬──────────┘           │
├─────────┴─────────────────┴───────────────────┴──────────────────────┤
│  CONTROL PLANE CORE  (framework-agnostic, zero framework imports)     │
│  ┌───────────┐  ┌──────────┐  ┌──────────────┐  ┌────────────────┐   │
│  │ Registry  │→ │ Router   │  │ PolicyEngine │  │ ApprovalService│   │
│  │ workflows │  │ run_id   │  │  (the PDP)   │  │  request/      │   │
│  │ + policies│  │ ctx build│  │  pure fn     │  │  resolve/wait  │   │
│  └───────────┘  └────┬─────┘  └──────┬───────┘  └───────┬────────┘   │
│  ┌───────────┐  ┌────┴─────┐  ┌──────┴───────┐          │            │
│  │ Tracer    │  │ RunContext│ │ BudgetLedger │          │            │
│  │ spans     │  │contextvar │ │ tokens/cost/ │          │            │
│  │ metrics   │  │           │ │ rate (stateful)│        │            │
│  └─────┬─────┘  └────┬──────┘ └──────┬───────┘          │            │
├────────┼─────────────┼───────────────┼──────────────────┼────────────┤
│  ADAPTER LAYER  (one module per backend; owns ALL framework imports)  │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐  │
│  │ langgraph_adapter│ │ crewai_adapter   │ │ autogen_adapter      │  │
│  │ + LLM shim       │ │ + LLM shim       │ │ + LLM shim           │  │
│  │ + tool wrapper   │ │ + tool wrapper   │ │ + tool wrapper       │  │
│  │ + gate node      │ │ + hook dispatch  │ │ + termination cond.  │  │
│  │ capabilities:    │ │ capabilities:    │ │ capabilities:        │  │
│  │  hitl=DURABLE    │ │  hitl=BLOCKING   │ │  hitl=SNAPSHOT       │  │
│  └────────┬─────────┘ └────────┬─────────┘ └──────────┬───────────┘  │
├───────────┼────────────────────┼─────────────────────-┼──────────────┤
│  ENFORCEMENT SEAMS  (inside the framework's own call path)            │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │ Seam A: model client   Seam B: tool object   Seam C: step cb │    │
│  │  every LLM call         every tool call       every step     │    │
│  │  → budget + PDP         → PDP + approval      → trace span   │    │
│  └──────────────────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────────┤
│  FRAMEWORKS (unmodified, real dependencies)                           │
│   langgraph 1.2.x      crewai 1.15.x       autogen-agentchat 0.7.x    │
├──────────────────────────────────────────────────────────────────────┤
│  STORES  (pluggable protocols, SQLite impl for v1)                    │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────────┐   │
│  │ RunStore   │ │ SpanStore  │ │ ApprovalSt.│ │ CheckpointStore  │   │
│  │ runs,      │ │ traces     │ │ requests + │ │ LangGraph        │   │
│  │ metrics    │ │            │ │ decisions  │ │ SqliteSaver /    │   │
│  │            │ │            │ │ (audit)    │ │ AutoGen state    │   │
│  └────────────┘ └────────────┘ └────────────┘ └──────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **Registry** | Load + validate `workflow.yaml` / `policy.yaml`; resolve `policy_id` → `Policy`; own `workflow_id` (author-declared, never generated) | Pydantic models + YAML loader; dict keyed by `workflow_id` |
| **Router** | Sole owner of `run_id` generation. Static pre-flight validation (declared tools ⊆ `allowed_tools`; `required_approval_nodes` exist). Select adapter by `backend_type`. Build `RunContext`. Own `resume()`. | ~120 LOC; a dict of `backend_type → Adapter` |
| **PolicyEngine (PDP)** | **Pure function**: `decide(PolicyContext) → Decision(ALLOW / DENY(reason) / REQUIRE_APPROVAL)`. No I/O, no framework imports, no clock reads (clock injected). | Pure Python; the one component with 100% test coverage and zero framework deps |
| **BudgetLedger** | The *stateful* half of policy: running token/cost totals per run, per-day rolling cost, rate-limit windows. Reads/writes `RunStore`. Feeds numbers into `PolicyContext`. | SQLite counters + in-memory cache; separated from PDP so PDP stays pure |
| **ApprovalService** | Create `ApprovalRequest`, persist it, expose `resolve(approval_id, decision, actor, note)`, expose `wait(approval_id, timeout)` for blocking backends. Owns the audit trail. | SQLite table + `asyncio.Event` / polling for `wait()` |
| **Tracer / Metrics** | Emit spans (`run_id`, `parent_span_id`, node/agent name, tokens, latency, tool outcome) into `SpanStore`. Aggregate to run-level metrics at finish. | Custom, but name attributes per **OTel GenAI semconv** (`gen_ai.*`) so an OTel exporter is a later drop-in |
| **RunContext** | Immutable dataclass carrying `run_id`, `workflow_id`, `policy`, and handles to PDP/ledger/tracer/approvals. Bound to a `contextvars.ContextVar`. | ~30 LOC; the single most load-bearing 30 LOC in the project (see Pattern 3) |
| **Adapter** | Translate `RunContext` + inputs into a *constructed, instrumented* framework object; execute it; map framework outcomes to `RunStatus`. Declare `AdapterCapabilities`. | One module per backend, ~200-350 LOC each, framework imports quarantined here |
| **Enforcement shims** | The actual PEPs. Live *inside* each adapter module (not a separate package — 6 small classes, one implementation each). | LLM subclass + tool wrapper per backend |

---

## Verified Extension Points Per Framework

This table is the factual foundation for every design decision below. All rows verified against current docs (Context7) except where noted.

| Concern | LangGraph 1.2.x | CrewAI 1.15.x | AutoGen AgentChat 0.7.x |
|---------|-----------------|---------------|-------------------------|
| **LLM interception (Seam A)** | Pass a custom `BaseChatModel`, or `CallbackHandler` via `config={"callbacks":[...]}` | `@before_llm_call` / `@after_llm_call` hooks — `LLMCallHookContext(agent, task, crew, llm, messages, iterations, response)`; **returning `False` blocks the call**. Also custom `BaseLLM` subclass. | Subclass `ChatCompletionClient` (ABC with `create()` / `create_stream()`); `CreateResult.usage` gives prompt/completion tokens |
| **Tool interception (Seam B)** | Wrap `BaseTool` / decorate the tool fn; or a dedicated tool-review node | `@before_tool_call` / `@after_tool_call` — `ToolCallHookContext(tool_name, tool_input, ...)`; **return `False` blocks**; has `context.request_human_input(prompt, default_message)` | Wrap `FunctionTool(func, description, name=...)` — wrap `func` before constructing |
| **Step/turn observation (Seam C)** | Node boundaries; `stream()` events; callbacks | `step_callback` (per agent step), `task_callback` (per task), `before/after_kickoff` | `run_stream()` async generator of messages; `TerminationCondition` |
| **Native pause + durable resume** | ✅ `interrupt(payload)` + `Command(resume=v)`; checkpointer (`SqliteSaver`) keyed by `thread_id`; `durability="sync"`; `interrupt_before/after`; `update_state(as_node=)`; time-travel via `get_state_history` | ❌ **None.** Only inline blocking via `request_human_input` | ⚠️ Partial: `Team.save_state()` / `load_state()`, `dump_component()` / `load_component()`; `pause()`/`resume()` exist but are **in-process only and marked experimental**; `HandoffTermination("user")` + `HandoffMessage` is the resumable idiom |
| **Hook registration scope** | Per-invocation (`config`) — clean | **Process-global** (`register_before_llm_call_hook`) or crew-scoped (`@before_llm_call_crew` in a `CrewBase`) — concurrency hazard, see Anti-Pattern 5 | Per-object (you construct the client/tools) — clean |
| **Serializable for resume** | State is the checkpoint; graph rebuilt from code | Crew rebuilt from code; no state snapshot | `dump_component()` requires every participant implement `_to_config`/`_from_config` |

**Two corrections to likely assumptions in the original spec:**

1. `register_reply` is **AutoGen v0.2 API** (`pyautogen`, now 0.10.x, legacy line). The current `autogen-agentchat` 0.7.x has no `register_reply`; the interception points are the model client, tool wrapping, and termination conditions. Design against 0.7.x.
2. CrewAI's `step_callback`/`task_callback` are **observation only** — they cannot block. Real enforcement in CrewAI requires the newer `crewai.hooks` module (`before_tool_call`/`before_llm_call`, block by returning `False`). Verified present in installed `crewai` 1.9.3 via introspection:
   `before_llm_call, after_llm_call, before_tool_call, after_tool_call, register_*_hook, unregister_*_hook, LLMCallHookContext, ToolCallHookContext`.
   **This is the single most important finding for the CrewAI adapter** — without it, CrewAI policy enforcement would be fake.

---

## Recommended Project Structure

```
src/eacp/
├── models.py                  # ALL schemas: Policy, Workflow, RunRecord, ApprovalRequest,
│                              # RunContext, Decision, AdapterCapabilities, Span. One file.
├── engine/
│   ├── registry.py            # YAML load + validate; workflow_id/policy_id resolution
│   ├── router.py              # run_id generation, pre-flight validation, dispatch, resume
│   ├── policy.py              # the PDP — pure decide(); no imports beyond models
│   ├── budget.py              # stateful token/cost/rate ledger
│   ├── approvals.py           # ApprovalService: request / resolve / wait
│   └── context.py             # ContextVar[RunContext] + bind_run() + current_run()
├── adapters/
│   ├── base.py                # Adapter Protocol + AdapterCapabilities — WRITTEN 9TH, NOT 1ST
│   ├── langgraph_adapter.py   # adapter + its LLM shim + its tool wrapper + gate node
│   ├── crewai_adapter.py      # adapter + hook dispatcher + LLM shim + tool wrapper
│   └── autogen_adapter.py     # adapter + ChatCompletionClient shim + FunctionTool wrapper
├── observability/
│   ├── tracer.py              # span emission, gen_ai.* attribute naming
│   ├── metrics.py             # run-level aggregation
│   └── store.py               # RunStore/SpanStore/ApprovalStore Protocols + SqliteStore
├── llm/
│   └── mock.py                # deterministic MockLLM/FakeModelClient — built EARLY (step 3.5)
├── evaluation/
│   └── benchmark.py           # same logical workflow × 3 backends → Markdown + JSON/CSV
└── cli.py                     # run / approve / deny / trace / benchmark
examples/
├── contract_review/           # LangGraph — workflow.yaml, policy.yaml, graph.py, run.py
├── sales_intel/               # CrewAI
└── incident_response/         # AutoGen
```

### Structure Rationale

- **`models.py` as one file, not a package.** Every component imports it; splitting it into `models/policy.py`, `models/run.py` etc. buys nothing and creates import-ordering friction. Split only when it passes ~400 lines.
- **Enforcement shims live inside their adapter module, not a separate `enforcement/` package.** Each shim has exactly one implementation and is meaningless without its adapter. A separate package would be six files with one class each and a shared import — pure ceremony. Keeping `crewai_adapter.py` as the single place that knows anything about CrewAI is the more valuable invariant.
- **`adapters/base.py` exists but is written ninth.** See Build Order. Writing the ABC first guarantees it encodes LangGraph's assumptions and then gets rewritten.
- **`llm/mock.py` is a first-class module, not test scaffolding.** It is what makes the entire control plane testable without API keys (a hard constraint in PROJECT.md), *and* it is the deterministic token/cost source that makes budget-enforcement tests assertable. It must return controllable `usage` numbers.
- **Framework imports appear in exactly three files.** This is checkable with one grep in CI and is the structural guarantee that the core is vendor-agnostic. Enforce it as a test.

---

## Architectural Patterns

### Pattern 1: Shared PDP + Injected Per-Backend PEPs

**This is the direct answer to "where should policy enforcement live?"**

Three options, and the third is right:

| Option | How | Why not / why yes |
|--------|-----|-------------------|
| **A. Policy inside each adapter** | Each adapter implements the rules | ❌ Three copies of the rules. They drift the first time a bug is fixed in one. The project's core claim — "one policy definition governs any backend" — becomes false. |
| **B. Shared middleware the adapter calls** | Adapter calls `policy.check(...)` at each interesting point | ⚠️ One rule set (good), but enforcement correctness depends on the adapter *remembering to call it*. A missed call is a **silent policy bypass** — the worst possible failure for a governance tool, because it looks like it's working. |
| **C. Shared PDP + shims injected into the framework's object graph** | Adapter swaps the model client and wraps the tool objects at construction time. The framework itself then calls your code on every LLM/tool invocation. | ✅ Recommended. You cannot forget to enforce, because enforcement lives on the object the framework invokes, not on a line of code you wrote. |

**The decisive advantage of C:** verification becomes *structural* instead of *behavioural*. Option B forces you to ask "did we call `check()` at every site?" — unanswerable without exhaustive integration tests. Option C lets you assert, per adapter, in one test: *every tool handed to the framework is an instance of our wrapper, and the model client is our shim.* That is a ~5-line test per adapter and it is the actual safety property.

```python
# engine/policy.py — pure. No framework imports. No I/O. Clock injected.
def decide(ctx: PolicyContext) -> Decision:
    if ctx.event == "tool_call":
        if ctx.tool_name in ctx.policy.forbidden_tools:
            return Decision.deny(f"tool '{ctx.tool_name}' is forbidden")
        if ctx.policy.allowed_tools and ctx.tool_name not in ctx.policy.allowed_tools:
            return Decision.deny(f"tool '{ctx.tool_name}' not in allowlist")
        if ctx.node_name in ctx.policy.required_approval_nodes:
            return Decision.require_approval(node=ctx.node_name)
    if ctx.event == "llm_call":
        if ctx.tokens_used_this_run >= ctx.policy.max_tokens_per_run:
            return Decision.deny("run token budget exhausted")
        if ctx.cost_today >= ctx.policy.max_cost_per_day:
            return Decision.deny("daily cost budget exhausted")
    return Decision.allow()
```

```python
# adapters/crewai_adapter.py — the PEP is wiring, not logic.
from crewai.hooks import register_before_tool_call_hook
from eacp.engine.context import current_run

def _tool_gate(hook_ctx) -> bool | None:
    run = current_run()                       # contextvar — see Pattern 3
    if run is None:
        return None                           # not an EACP-managed run; don't interfere
    d = run.pdp.decide(run.policy_context(event="tool_call",
                                          tool_name=hook_ctx.tool_name))
    run.tracer.policy_decision(d, tool=hook_ctx.tool_name)
    if d.is_deny:
        return False                          # CrewAI blocks the tool call
    if d.needs_approval:
        return run.approvals.block_until_decided(d, hook_ctx)   # tier-3 blocking
    return None

register_before_tool_call_hook(_tool_gate)    # registered ONCE, process-global
```

**Trade-off / honest limitation:** injection only governs what the workflow *lets you inject*. A workflow author who constructs `ChatOpenAI()` inside a node body, or imports a tool directly, bypasses the control plane entirely. Mitigate with an **adapter contract** — the registered entrypoint must be a factory `build(model, tools) -> Graph | Crew | Team` — validated at registry load. But state this plainly in the README:

> **EACP is a governance layer, not a security sandbox.** It is in-process and cooperative. It enforces against mistakes, drift, and misconfiguration — not against an adversarial workflow author. A real security boundary requires an out-of-process PEP (tool-execution proxy / OPA sidecar), which is out of scope for v1.

Saying this out loud is a credibility asset for an OSS contribution, not a weakness. Reviewers will find it anyway.

---

### Pattern 2: Capability-Tiered HITL (the hard problem, stated honestly)

**Verdict up front: a uniformly durable pause/resume across these three frameworks is not achievable without forking one of them. Do not promise it.**

The three frameworks sit at genuinely different points, and the difference is architectural, not a matter of effort:

**Tier `DURABLE` — LangGraph.** Real suspend-to-storage.
- Gate node calls `interrupt(payload)`; graph compiled with `SqliteSaver`; `thread_id = run_id`; `durability="sync"`.
- `execute()` returns `SUSPENDED(approval_id)`. **The process can exit.** Hours later: `graph.invoke(Command(resume=decision), config={"configurable": {"thread_id": run_id}})`.
- **Verified gotcha that shapes the design:** resume **re-executes the entire node from the top**, not from the line after `interrupt()`. Therefore the gate node must contain *nothing but* the interrupt and the branch on the decision; the irreversible action belongs in the following node. Additionally, multiple `interrupt()` calls in one node are matched to resume values **by index**, so ordering must be deterministic. Encode both as rules in the adapter's docstring and in TUTORIAL_LANGGRAPH.md.

**Tier `SNAPSHOT` — AutoGen.** Resumable, but only at message boundaries.
- Approval point ends the run via a `TerminationCondition` (or `HandoffTermination("user")` with `handoffs=["user"]`). Then `state = await team.save_state()` and `cfg = team.dump_component()`, both persisted under `run_id`.
- Resume: `Team.load_component(cfg)` → `await team.load_state(state)` → `await team.run(task=HandoffMessage(content=decision, ...))`.
- **Real limitation, not hand-waved:** the snapshot boundary is a *message* boundary. You cannot suspend between "the model emitted a tool call" and "the tool executed." So a tool-triggered approval in AutoGen has only two honest implementations: (a) the tool wrapper blocks in-process (loses durability), or (b) the workflow is authored so the risky action is *requested as a handoff/message* and executed in a separate turn after approval (durable, but constrains the workflow author). The control plane must document (b) as the AutoGen authoring pattern — it cannot hide the constraint.
- Secondary constraint: `dump_component()` requires every participant to be component-serializable (custom agents need `_to_config`/`_from_config`). This limits how exotic the incident-response example can get.

**Tier `BLOCKING` — CrewAI.** No suspend at all.
- `@before_tool_call` + `context.request_human_input(...)` → return `False` to block. This is *real* enforcement (verified), and it satisfies "certain actions blocked without approval." But it blocks the calling thread, there is no checkpoint, and if the process dies the run is lost — restarting re-runs from task 1.
- The only durable option is **segmentation**: the author splits the crew at the approval boundary into `crew_pre` / `crew_post`; the control plane persists `crew_pre`'s output, raises the approval, and later calls `crew_post.kickoff(inputs=approved_output)` under the same `run_id`. Durable, but (i) requires authoring cooperation, (ii) loses accumulated agent short-term memory across the boundary unless explicitly threaded through inputs, and (iii) redefines "approval node" for CrewAI to mean *task boundary*, not *tool call*.
- **Hard scope boundary:** do **not** subclass or reimplement `CrewAgentExecutor` to add checkpointing. That is forking the framework, and CrewAI went 1.0 → 1.15 in months — it will break on nearly every minor release. This is the single largest scope trap in the project.

**The design that makes this shippable:**

```python
class HitlDurability(StrEnum):
    DURABLE   = "durable"    # process may die; resume from persisted checkpoint
    SNAPSHOT  = "snapshot"   # resumable at message/turn boundaries only
    BLOCKING  = "blocking"   # in-process wait; no durability
    SEGMENTED = "segmented"  # durable only across author-declared segment boundaries

@dataclass(frozen=True)
class AdapterCapabilities:
    hitl: HitlDurability
    approval_granularity: Literal["tool_call", "node", "task", "turn"]
    resumable_after_process_exit: bool
```

What **is** uniform, and should be (this is the real win):
- the `ApprovalRequest` **record** — same schema, same store, same audit trail, same CLI (`eacp approve <id>`), same `compliance_tags`, regardless of backend;
- the **policy declaration** — `required_approval_nodes` is written once and means the same thing;
- the **decision semantics** — approve/deny/timeout, who, when, why.

What is **not** uniform: the durability guarantee. Surface it in `AdapterCapabilities`, print it in the benchmark table, and give it a section in `DECISION_FRAMEWORK.md`.

**Reframe:** this asymmetry is the most publishable finding in the whole project. "We tried to build uniform durable HITL across the three leading frameworks; here is precisely where each one can and cannot suspend, with a working implementation of the best available option per backend" is a far stronger contribution than a leaky abstraction that claims parity. Lead with it.

---

### Pattern 3: Run Identity via ContextVars

**Problem:** the enforcement seams sit deep inside framework internals and do not receive your `RunContext`. CrewAI's global hook gets an `LLMCallHookContext` (crew/agent/task/llm — no `run_id`). AutoGen's `ChatCompletionClient.create()` receives only messages and tools. You cannot add a parameter.

**Solution:** carry run identity out-of-band.

```python
# engine/context.py
_current: ContextVar[RunContext | None] = ContextVar("eacp_run", default=None)

@contextmanager
def bind_run(ctx: RunContext):
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)

def current_run() -> RunContext | None:
    return _current.get()
```

This also solves CrewAI's process-global hook registration: register **one** hook at import time that dispatches on `current_run()` and no-ops when it's `None`. Concurrent runs stay isolated without re-registering hooks.

**Two real hazards, both worth a comment in the code:**
1. `contextvars` propagate into `asyncio` tasks (context is copied at task creation) but **not** into threads started by a `ThreadPoolExecutor` unless you propagate explicitly (`contextvars.copy_context().run`). CrewAI uses threads for `kickoff_for_each_async` and some delegation paths. Wrap any thread hand-off, or the `RunContext` silently vanishes and enforcement becomes a no-op — a silent bypass.
2. Never make `RunContext` mutable. Mutation across concurrent runs is exactly the bug class contextvars are meant to prevent.

---

### Pattern 4: OTel-Shaped Spans, Custom Backend

Emit your own spans into SQLite (no OTel dependency in v1 — YAGNI), but **name the attributes per the OpenTelemetry GenAI semantic conventions** (`gen_ai.operation.name`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.request.model`, `gen_ai.tool.name`). Cost is ~zero now and makes "export to OTel/LangSmith/Phoenix" a later adapter rather than a migration. OTel's GenAI WG is actively converging on cross-framework agent conventions covering exactly CrewAI/AutoGen/LangGraph, so this bet is cheap and directionally safe.

Span hierarchy: `run` → `step` (node / task / turn) → `llm_call` | `tool_call` | `policy_decision` | `approval`. Emitting `policy_decision` and `approval` as first-class spans is what makes the trace an **audit log**, not just a debugging aid — and audit is the enterprise selling point.

---

## Data Flow

### Run Flow

```
$ eacp run contract_review --input contract.json
    │
    ▼
Registry.load()                      workflow_id, policy_id ← YAML (human-authored, stable)
    │                                Workflow{backend_type, entrypoint, policy_id}
    ▼
Router.run(workflow, inputs)
    ├─ run_id = uuid7()              ◄── GENERATED HERE. Once. Before any adapter is touched.
    ├─ pre-flight validation         declared tools ⊆ allowed_tools?
    │                                required_approval_nodes exist in workflow?
    │                                FAIL → never launched, status=REJECTED, no tokens spent
    ├─ RunStore.create(run_id, workflow_id, backend_type, policy_id, RUNNING)
    ├─ ctx = RunContext(run_id, workflow_id, policy, pdp, ledger, tracer, approvals)
    └─ with bind_run(ctx):           ◄── contextvar set here, covers everything below
         adapter.execute(ctx, inputs)
              │
              ├─ build framework object, INJECTING:
              │     model client → LLM shim        (Seam A)
              │     tools        → tool wrappers   (Seam B)
              │     callbacks    → tracer taps     (Seam C)
              │
              ├─ framework runs ──┬─ LLM call  → shim: ledger.charge(usage)
              │                   │              → pdp.decide → ALLOW | DENY
              │                   │              → tracer.span(llm_call)
              │                   │
              │                   ├─ tool call → wrapper: pdp.decide
              │                   │              → ALLOW → execute
              │                   │              → DENY  → raise PolicyViolation
              │                   │              → REQUIRE_APPROVAL ↓
              │                   │
              │                   └─ step end  → tracer.span(step)
              │
              └─ returns COMPLETED | FAILED | SUSPENDED(approval_id) | DENIED(reason)
    │
    ▼
RunStore.finish(run_id, status, metrics)   latency, tokens, cost, steps,
                                           approvals_triggered, tool_success_rate
```

### Approval / Resume Flow

```
REQUIRE_APPROVAL decision
    │
    ▼
ApprovalService.request(run_id, node, payload, compliance_tags)
    ├─ approval_id = uuid7()         ◄── GENERATED HERE
    └─ ApprovalStore.insert(PENDING)
    │
    ├── tier BLOCKING (CrewAI) ──────► await wait(approval_id) in-process; process must live
    │
    └── tier DURABLE / SNAPSHOT ─────► persist backend suspend artifact:
             LangGraph: nothing extra — SqliteSaver already holds it (thread_id = run_id)
             AutoGen:   save_state() + dump_component() → CheckpointStore[run_id]
         adapter returns SUSPENDED; Router sets status=AWAITING_APPROVAL; process exits

$ eacp approve <approval_id> --note "legal signed off"
    │
    ▼
ApprovalService.resolve(approval_id, APPROVED, actor, note, ts)   ◄── immutable audit row
    │
    ▼
Router.resume(run_id)
    ├─ RunStore.get(run_id) → workflow_id, backend_type, policy_id
    ├─ rebuild RunContext with the SAME run_id (resume_seq += 1)
    └─ adapter.resume(ctx, approval)
            LangGraph: graph.invoke(Command(resume=decision), thread_id=run_id)
            AutoGen:   load_component + load_state + run(HandoffMessage(decision))
            CrewAI:    crew_post.kickoff(inputs=persisted_segment_output)
```

### ID Ownership — Single Table of Truth

| ID | Generated by | When | Shape | Notes |
|----|--------------|------|-------|-------|
| `workflow_id` | **Human**, in YAML | authoring time | slug | Registry key. Must be stable across runs — **never generate it**. Generating it breaks history, benchmarks, and policy attachment. |
| `policy_id` | **Human**, in YAML | authoring time | slug | Referenced by workflows; many-to-one. |
| `run_id` | `Router` | at `run()` entry, **before** the adapter | uuid7 / ULID | Time-sortable so run history lists without an index-only sort. The single correlation key across all stores. |
| `thread_id` (LangGraph) | derived | — | `= run_id` | Keep 1:1. Do not invent a second identifier — debugging a two-ID scheme across checkpointer and run store is misery. |
| `approval_id` | `ApprovalService` | on first `REQUIRE_APPROVAL` | uuid7 | The CLI handle. Multiple per run allowed. |
| `span_id` / `parent_span_id` | `Tracer` | per step/call | uuid7 | Parent chain gives the trace tree. |
| `resume_seq` | `Router` | per resume | int, from 0 | Distinguishes replayed node executions in the trace — essential given LangGraph's node re-execution on resume. Without it the trace looks corrupted. |

---

## Suggested Build Order

Ordered by hard dependency. The two non-obvious claims are marked ★.

| # | Build | Depends on | Why here |
|---|-------|-----------|----------|
| 1 | `models.py` — Policy, Workflow, RunRecord, ApprovalRequest, Decision, Span schemas | — | Everything imports it. Schema-first is genuinely required: the PDP is a function of the policy schema. |
| 2 | Store protocols + `SqliteStore` | 1 | The ledger, approvals, and tracer all need persistence. Thin. |
| 3 | **PolicyEngine (PDP)** — pure `decide()` | 1 | ★ **Before any adapter.** It has zero framework dependencies, so it can be fully unit-tested against a table of `(PolicyContext, expected Decision)` cases on day one. If the rules are wrong, everything downstream enforces the wrong thing. |
| 4 | `llm/mock.py` — deterministic mock model with controllable `usage` | 1 | Unblocks testing 5–10 without API keys (PROJECT.md constraint) *and* makes budget assertions deterministic. Cheap; pulling it earlier than instinct suggests pays for itself immediately. |
| 5 | `BudgetLedger` | 1,2,3,4 | The stateful half of enforcement. Testable end-to-end with the mock. |
| 6 | Tracer + metrics + `RunContext`/contextvars | 1,2 | Adapters need somewhere to emit and something to read identity from. |
| 7 | `ApprovalService` + `eacp approve/deny` CLI | 1,2 | Must exist before the first adapter, because the LangGraph adapter's whole point is exercising the approval round-trip. Building the CLI now also means approvals are testable without any framework. |
| 8 | **LangGraph adapter — concrete, no ABC** | 1–7 | ★ Richest native support (`interrupt` + checkpointer), so it validates the hardest path (durable suspend → CLI approve → resume) with the framework doing the heavy lifting. Also delivers the contract-review example, the strongest demo. |
| 9 | **CrewAI adapter — concrete, still no ABC** | 1–7 | ★ **Second, not third.** CrewAI is the *worst* HITL case. Hitting the no-checkpoint wall here forces the capability-tier design (Pattern 2) into existence while only one adapter is written. If you build AutoGen second, you get two snapshot-ish backends, design a "durable resume" interface, and then CrewAI invalidates it — a late rewrite of the core abstraction. |
| 10 | Extract `adapters/base.py` — `Adapter` Protocol + `AdapterCapabilities` | 8,9 | Extract from two *working, maximally different* implementations. Writing this first guarantees it encodes LangGraph's assumptions. Two points define the line; the third tests it. |
| 11 | AutoGen adapter, against the extracted interface | 10 | Now the interface gets *proven* rather than *designed*. If AutoGen needs no interface change, the abstraction is real; if it does, you learn cheaply with 2 of 3 done. |
| 12 | Three examples + per-example CLI | 8,9,11 | Each example is the acceptance test for its adapter. |
| 13 | Benchmark runner | 12 | Needs all three running the same logical workflow. |
| 14 | Docs (README, DECISION_FRAMEWORK, 3 tutorials, PR text) | 13 | `DECISION_FRAMEWORK.md` and the README's headline claims should be written *from measured benchmark output*, not from expectations. This is also where the HITL capability matrix lands. |

**Critical path summary:** policy schema → PDP → mock LLM → approvals → LangGraph adapter → CrewAI adapter → *then* the adapter interface → AutoGen → examples → benchmarks → docs.

---

## Scaling Considerations

For a reference implementation, "scale" means concurrent runs and backend count, not end users.

| Scale | Architecture adjustments |
|-------|--------------------------|
| 1 run at a time (v1 target, CLI) | SQLite + in-process everything is correct. No queue, no worker pool. |
| ~10 concurrent runs (same process, async) | contextvar isolation must be verified — especially CrewAI's global hooks and any `ThreadPoolExecutor` hand-off. Add `WAL` mode to SQLite. Rate-limit windows need a lock. |
| ~100 concurrent runs / multi-process | SQLite write contention on the span table is the first real wall. Batch span writes; move `BudgetLedger` behind a single writer or Redis counters. `ApprovalService.wait()` must stop being an in-process `Event` and become store polling. |
| Multi-tenant / hosted | Out of scope per PROJECT.md. Would require out-of-process PDP (OPA sidecar), real queue, and Postgres. The store protocols and the pure PDP are what make that a later swap rather than a rewrite — which is the only reason to care now. |

### Scaling Priorities

1. **First bottleneck: span write volume to SQLite.** A chatty agent emits hundreds of spans per run. Fix by batching writes at step boundaries, not per event. Cheap to add later *if* the tracer's write path is a single method.
2. **Second bottleneck: `BudgetLedger` read-modify-write on every LLM call.** Fix by caching per-run counters in `RunContext` and flushing on step boundaries; daily cost stays a store read with a short TTL.

Neither is worth building for now. Both are worth *not designing out* — which means keeping span writes and ledger updates behind one method each.

---

## Anti-Patterns

### Anti-Pattern 1: The Neutral Workflow DSL

**What people do:** define an EACP-native workflow format (nodes, edges, roles) that compiles down to a LangGraph graph, a CrewAI crew, and an AutoGen team.
**Why it's wrong:** it converges on the intersection of the three frameworks' capabilities, which is roughly "call an LLM in a sequence" — discarding the exact things that make each framework worth using (LangGraph's conditional edges and checkpoints, CrewAI's delegation, AutoGen's free-form conversation). It is also unbounded work: every framework feature becomes a DSL feature request. And it makes the benchmark meaningless, because you'd be benchmarking your lowest-common-denominator compiler rather than the frameworks.
**Do this instead:** workflows are authored **natively** in each framework. The `workflow.yaml` carries only metadata (`id`, `name`, `backend_type`, `entrypoint`, `policy_id`) and points at a Python factory. The unified thing is the *control plane*, not the *authoring model*. "Same logical workflow, three native implementations" is also the only honest basis for a cross-framework benchmark.

### Anti-Pattern 2: Validation-Only Policy

**What people do:** check the policy at registration/startup, log "policy attached", and let the run proceed unguarded.
**Why it's wrong:** it is precisely the failure the project exists to fix (PROJECT.md: "enforced for real, not just documented"). A tool allowlist that is only checked against *declared* tools does not stop an agent from calling a tool it discovered at runtime.
**Do this instead:** static validation at registration **and** runtime enforcement at Seams A and B. Keep both — static validation is what lets a bad run fail before spending tokens.

### Anti-Pattern 3: Approval Theatre

**What people do:** print "⚠️ approval required" then continue; or implement approval only at the outer `run()` boundary.
**Why it's wrong:** unfalsifiable governance. Worse than none, because it creates false confidence.
**Do this instead:** the approval must sit on the *blocking return path* of the seam — CrewAI's hook returning `False`, LangGraph's `interrupt()` before the action node, AutoGen's termination before the action turn. Test it by asserting the side effect **did not happen** on deny. That single assertion per adapter is the project's core credibility test.

### Anti-Pattern 4: Wrapping Only the Public Entry Point

**What people do:** `try: crew.kickoff() except: ...` with timing around it, and call that instrumentation.
**Why it's wrong:** gives run-level latency and nothing else — no per-step trace, no token accounting, no tool interception, no approval gate. Every requirement in PROJECT.md lives *inside* the loop.
**Do this instead:** inject at the seams (Pattern 1). If a framework offers no seam for a concern, say so in `AdapterCapabilities` rather than faking it.

### Anti-Pattern 5: Ignoring CrewAI's Process-Global Hook Registry

**What people do:** call `register_before_tool_call_hook(...)` per run, closing over that run's context.
**Why it's wrong:** registration is process-global and additive. N runs register N hooks; every hook then fires for every run, cross-contaminating policy decisions and traces. Symptoms look like flaky tests, not like a bug.
**Do this instead:** register exactly one hook at module import; dispatch on `current_run()`; return `None` (no-op) when unbound. Use the `unregister_*` functions only in test teardown.

### Anti-Pattern 6: Side Effects Before `interrupt()`

**What people do:** in a LangGraph gate node, do the work, then `interrupt()` for approval.
**Why it's wrong:** verified behaviour — resume re-runs the node **from the top**. Everything before `interrupt()` executes again. An approval gate on "send contract" that emails before the interrupt sends the email twice, and sends it even on deny.
**Do this instead:** gate nodes contain the interrupt and the branch, nothing else. Irreversible actions live in the *next* node. Make this a documented adapter rule and a tutorial callout.

---

## Integration Points

### External Dependencies

| Dependency | Integration pattern | Notes / gotchas |
|-----------|--------------------|-----------------|
| `langgraph` 1.2.x | Custom `BaseChatModel` + wrapped tools + `SqliteSaver` + `interrupt()` | Best-supported backend. Node re-execution on resume is the one sharp edge. `durability="sync"` for real durability. |
| `crewai` 1.15.x | `crewai.hooks` global hooks (block-capable) + `step_callback`/`task_callback` for tracing | Fast-moving (1.0 → 1.15 in months) — **pin exactly**. `crewai.hooks` is the load-bearing API; verify its presence at adapter import and fail loudly with a version hint if absent. |
| `autogen-agentchat` 0.7.x | Custom `ChatCompletionClient` + wrapped `FunctionTool` + `TerminationCondition` + `save_state`/`dump_component` | **AutoGen entered maintenance mode (Oct 2025); Microsoft Agent Framework 1.0 GA'd April 2026 as its successor.** Two consequences: (a) the API is frozen, so the adapter is a *stable* target — an upside; (b) a 4th adapter for `agent-framework` is the obvious follow-up and is the best proof the adapter interface generalizes. Note this honestly in `DECISION_FRAMEWORK.md`; reviewers will know. |
| SQLite (stdlib `sqlite3`) | `RunStore` / `SpanStore` / `ApprovalStore` protocol impls | Enable WAL. Keep protocols narrow (4–6 methods) so Postgres is a later drop-in, per PROJECT.md. |
| OTel GenAI semconv | Attribute **naming** only in v1; no dependency | Zero-cost future-proofing for a real exporter. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| CLI ↔ Router | Direct call | No API server in v1 (out of scope). |
| Router ↔ Adapter | Direct call, `RunContext` passed explicitly | The only place an adapter is referenced. Dispatch is a dict on `backend_type`. |
| Adapter ↔ Framework | Construction-time injection, **not** runtime calls | The core structural guarantee of Pattern 1. Testable: assert all tools are wrapped. |
| Shim ↔ PDP | Direct call to a pure function, run identity via **contextvar** | The shim cannot receive `RunContext` as a parameter — framework signatures are fixed. |
| Everything ↔ Stores | Protocol (`typing.Protocol`), never the concrete class | The pluggability requirement. One `Protocol` per store, not a god-interface. |
| Core ↔ Frameworks | **Forbidden.** Framework imports only in `adapters/*.py` | Enforce with a CI test that greps for `langgraph`/`crewai`/`autogen` imports outside `adapters/`. Cheap, and it's the vendor-agnostic claim made checkable. |

---

## Confidence and Gaps

| Claim | Confidence | Basis |
|-------|-----------|-------|
| CrewAI `before_tool_call`/`before_llm_call` hooks exist and can block | **HIGH** | Direct introspection of installed `crewai` 1.9.3 + current docs |
| LangGraph `interrupt`/`Command(resume=)`/checkpointer supports durable suspend | **HIGH** | Official LangChain docs via Context7 |
| LangGraph resume re-executes the whole node | **HIGH** | Official interrupts docs + multiple independent write-ups |
| AutoGen 0.7.x has no `register_reply`; interception is via `ChatCompletionClient` / tools / termination | **HIGH** | `autogen_core.models._model_client` source via Context7 + v0.2→v0.4 migration guide |
| AutoGen `save_state`/`load_state`/`dump_component` enable message-boundary resume | **HIGH** | `Team` ABC source + migration guide |
| AutoGen is in maintenance mode; MAF is the successor | **MEDIUM-HIGH** | Multiple secondary sources agree, consistent with the upstream README; exact dates not verified against a primary announcement |
| PDP/PEP split is the right policy architecture | **HIGH** | Mature pattern (XACML, OPA); directly applicable |
| No prior art exists for uniform durable HITL across these three | **MEDIUM** | Searched; found framework comparisons and agent-gateway/OPA work, but no multi-framework control plane solving cross-backend durable suspend. Absence of evidence — treat as "likely novel," which is good for the contribution and bad for borrowing solutions. |

**Gaps for phase-level research:**
- Exact cost-attribution mechanics per backend (does CrewAI's `after_llm_call` context expose token usage directly, or must the LLM shim compute it?). Needs a code spike, not more reading.
- Whether CrewAI's `request_human_input` is usable from an async context without blocking the event loop.
- Whether AutoGen `dump_component()` round-trips cleanly for the incident-response agent set, or whether custom `_to_config` is required.
- Whether the `build(model, tools)` entrypoint contract is expressible for all three without feeling unnatural to framework-native authors. Resolve during step 10 (interface extraction).

---

## Sources

- LangGraph docs — interrupts, checkpointers, fault tolerance, functional API determinism: https://docs.langchain.com/oss/python/langgraph/interrupts (via Context7 `/websites/langchain_oss_python_langgraph`)
- LangGraph HITL double-execution analysis: https://blog.raed.dev/posts/langgraph-hitl/
- CrewAI docs — execution hooks, LLM hooks, tool hooks: https://docs.crewai.com/v1.15.2/en/learn/execution-hooks (via Context7 `/llmstxt/crewai_llms_txt`)
- CrewAI 1.9.3 `crewai.hooks` — verified by local introspection
- AutoGen — `Team` ABC, `ChatCompletionClient` ABC, component config, HITL tutorial, v0.2→v0.4 migration: https://microsoft.github.io/autogen/stable/ (via Context7 `/websites/microsoft_github_io_autogen_stable`)
- AutoGen maintenance-mode status and Microsoft Agent Framework succession: https://github.com/microsoft/autogen, https://www.langchain.com/resources/langchain-vs-autogen
- OpenTelemetry AI agent observability and GenAI semantic conventions: https://opentelemetry.io/blog/2025/ai-agent-observability/
- OpenInference vs OTel GenAI conventions for agent tracing: https://www.arthur.ai/column/openinference-vs-opentelemetry-genai-conventions-agent-tracing
- PDP/PEP and OPA for agent authorization: https://www.permit.io/blog/opa-for-protecting-ai-agents-and-agentic-stacks, https://tianpan.co/blog/2026/04/25/policy-as-code-agent-permissions-opa-rego
- Package versions via PyPI (2026-09-24): `langgraph` 1.2.12, `crewai` 1.15.22, `autogen-agentchat` 0.7.5, `agent-framework` 1.19.0

---
*Architecture research for: multi-framework agent control plane (EACP)*
*Researched: 2026-09-24*
