# Pitfalls Research

**Domain:** Vendor-agnostic control plane / governance layer over multiple competing agent frameworks (LangGraph, CrewAI, AutoGen)
**Researched:** 2026-09-24
**Confidence:** HIGH on framework/packaging state (verified against live PyPI metadata + dependency resolver + official docs). MEDIUM on abstraction-design and benchmarking pitfalls (synthesis of multiple credible sources + academic literature). MEDIUM-HIGH on enforcement-point pitfalls (official docs + community issue threads).

---

## Verified Ground Truth (as of 2026-09-24)

This section is the factual basis for Pitfalls 1 and 2. All figures were obtained by querying PyPI JSON metadata and running `uv pip compile` resolutions locally, not from training data.

### The "AutoGen" package namespace — four different things

| `pip install` name | Latest version | Import name | Actually maintained by | Status |
|---|---|---|---|---|
| `autogen-agentchat` | **0.7.5** (last stable **2025-09-30**) | `autogen_agentchat` (+ `autogen_core`, `autogen_ext`) | Microsoft | **Maintenance mode. No new features.** ~12 months without a release. |
| `pyautogen` | 0.10.0 (2025-07-15) | proxy → `autogen_agentchat>=0.6.4` | Microsoft-aligned proxy shim | Stale proxy; inherits AutoGen's maintenance status |
| `autogen` | **0.14.1** (2026-06-30) | `autogen` | AG2 (`github.com/ag2ai/ag2classic`) | AG2 **Classic** line — the `ConversableAgent` / `GroupChat` API. Maintained, but frozen surface. |
| `ag2` | **1.1.0** (released **2026-09-24**) | `ag2` | AG2 (`github.com/ag2ai/ag2`) | Actively developed mainline. **Not a drop-in upgrade from Classic** — agent model, orchestration, and imports all changed. |

Microsoft's `microsoft/autogen` README states verbatim: *"AutoGen is now in maintenance mode. It will not receive new features or enhancements and is community managed going forward."* and *"New users should start with Microsoft Agent Framework."* Microsoft Agent Framework (`pip install agent-framework`) shipped 1.0 on 2026-04-03 as the declared successor to both AutoGen and Semantic Kernel Agents.

AG2 v1.0 removed the classic namespace from the main repo: the top-level import is now `ag2`, and `import autogen` only works if you install the separate `autogen` (ag2classic) package.

**Direct consequence for this project:** `PROJECT.md` line 27 currently reads "real `autogen`/`pyautogen` or `autogen-agentchat` dependency" as if these were interchangeable alternatives. They are three different codebases with three different import roots and three different maintenance trajectories. This must be decided, not deferred.

### Dependency weight and resolvability (verified with `uv pip compile`)

| Requirement | Transitive packages (linux x86_64, py3.12) |
|---|---|
| `langgraph==1.2.12` alone | **38** |
| `crewai==1.15.22` alone | **134** |
| `autogen==0.14.1` (AG2 Classic) alone | **22** |
| `ag2==1.1.0` alone | **14** |
| `autogen-agentchat==0.7.5` alone | **11** |
| **All three together** | **155** |

CrewAI alone drags in `chromadb`, `lancedb`, `onnxruntime`, `kubernetes`, `pyarrow`, `numpy`, `tokenizers`, `grpcio`, `protobuf`, `uvicorn`, `mcp`, `textual`, and `uv` itself.

**Resolution failures found empirically:**
- **macOS x86_64 (Intel) — hard failure.** `crewai==1.15.22` requires `lancedb>=0.29.2,<0.30.1`; no wheel in that range publishes a `macosx_*_x86_64` tag. Resolution is *unsatisfiable*, not slow. Linux x86_64, linux aarch64, and macOS arm64 all resolve fine.
- **Python ceiling.** `crewai` declares `requires_python = <3.14,>=3.10`. The project constraint says "Python 3.11+"; CrewAI caps the upper end.
- **Transitive pin pull-down.** Adding `autogen-core==0.7.5` (which pins `protobuf~=5.29.3`) drags the whole environment's `protobuf` from `7.36.2` down to `5.29.6`. It resolves, but a Microsoft-AutoGen adapter silently constrains ChromaDB's protobuf for everyone.
- `autogen-agentchat` pins `autogen-core==0.7.5` **exactly** (`==`, not `~=`), so the agentchat/core/ext trio must be upgraded as an atomic unit.

### Release cadence (churn signal)

- `crewai`: **1.15.22**, with a nightly `1.15.22.devYYYYMMDD` published *every single day*. Went 1.1.0 → 1.15.x within months. Breaking changes landed between 0.47.x and 1.0.0 (`crew.kickoff()` return type changed from `TaskOutput` to `dict`; tools must inherit `BaseTool` or use `@tool` with explicit return type hints; `max_iter` default changed).
- `langgraph`: **1.2.12**, requires `langchain-core>=1.4.7,<2`. `Interrupt` was reduced from 4 fields to 2 (`value`, `id`) — `resumable`, `ns`, `when` are gone.
- `ag2`: **1.1.0 shipped the same day this research was performed.**

None of these three are stable targets. Two of the four candidate AutoGen packages are stale and one is a week old.

---

## Critical Pitfalls

### Pitfall 1: Building the "AutoGen adapter" against a sunset package

**What goes wrong:**
You `pip install autogen-agentchat`, write `autogen_agentchat.agents.AssistantAgent` + `RoundRobinGroupChat`, ship a tutorial, and submit it as an ecosystem contribution. A reviewer immediately notes that Microsoft put AutoGen in maintenance mode, that the package hasn't had a release in a year, and that new users are officially directed to Microsoft Agent Framework. The "serious contribution to the AutoGen ecosystem" framing collapses — you contributed to an ecosystem that was sunset. Alternatively you pick `import autogen` (AG2 Classic) and now your `GroupChat` code is against a deliberately frozen legacy surface while `ag2` 1.x is where development happens.

**Why it happens:**
Every tutorial, blog post, and LLM's training data says "AutoGen." The name maps to four packages and the mapping changed twice (the AG2 fork inherited `autogen`/`pyautogen` on PyPI, then `pyautogen` was repointed at Microsoft's `autogen-agentchat`, then AG2 1.0 moved off the `autogen` import entirely). Nobody checks which one they installed because all four "work."

**How to avoid:**
Decide explicitly in the stack phase, write the decision and the rejected alternatives into `DECISION_FRAMEWORK.md`, and name the adapter after the *package*, not the brand. Concretely:
- Name the module `ag2_adapter.py` or `autogen_classic_adapter.py` — **not** `autogen_adapter.py`. The ambiguous name is itself the bug.
- Put the exact pip name + version + import root in the adapter docstring.
- Recommended default: **`ag2==1.1.x`** (actively developed, tiny dependency footprint of 14 packages, `import ag2`). Second choice: `autogen==0.14.x` (AG2 Classic) if the incident-response example genuinely needs `GroupChat`/`ConversableAgent` semantics and you want the API most readers recognise — but then say "AG2 Classic" in the docs, never "AutoGen."
- Do **not** build the v1 adapter against `autogen-agentchat`. If you want Microsoft-lineage support, the forward-looking target is `agent-framework` (MAF 1.0), and that is a *fourth* adapter — out of scope per PROJECT.md.
- Add an honest paragraph to `DECISION_FRAMEWORK.md` titled "The AutoGen naming situation." This is the single highest-value piece of documentation in the whole project; nobody else has written it clearly and platform teams are actively confused by it.

**Warning signs:**
- The dependency spec says `autogen` or `pyautogen` without a version pin.
- Anyone on the project says "AutoGen" without qualifying which package.
- The adapter imports succeed but the tutorial's API doesn't match the linked docs site.
- `pip index versions <pkg>` shows the latest release is more than ~4 months old.

**Phase to address:**
**Phase 1 (stack/scaffold) — blocking.** This decision changes module names, example code, docs, dependency extras, and the project's entire positioning. It cannot be deferred to the adapter phase.

---

### Pitfall 2: Treating all three frameworks as one installable environment

**What goes wrong:**
`pyproject.toml` lists `langgraph`, `crewai`, and an AutoGen package as hard dependencies. The result: a 155-package environment, an install that pulls ONNX Runtime and the Kubernetes client to run a contract-review demo, a hard resolution failure on Intel macOS, and a CI job where 90% of the wall clock is `pip install`. Worse, a CrewAI nightly (published *daily*) or a `langchain-core` minor bump breaks CI on a day you changed nothing, and you can't tell which of three frameworks broke because they all live in one env.

**Why it happens:**
It's the path of least resistance, and it works on the author's machine (Apple Silicon or Linux). The reference-implementation framing ("adapters must be real, not stubbed") gets misread as "all adapters must be installed simultaneously."

**How to avoid:**
- **Optional extras, not hard deps.** Core package depends only on `pydantic` + stdlib. `pip install eacp[langgraph]`, `eacp[crewai]`, `eacp[ag2]`, `eacp[all]`. The core control plane must be installable and testable with zero agent frameworks present — that is the strongest possible demonstration that the governance layer is genuinely vendor-agnostic.
- **Lazy imports inside adapter modules.** `import langgraph` happens inside the adapter module body, and the adapter registry discovers adapters by attempting import and recording failures. Never at package `__init__` level. The tell-tale symptom of getting this wrong: `import eacp` raises `ModuleNotFoundError: crewai`.
- **CI matrix by adapter, not one fat job.** Four jobs: `core` (no frameworks — must pass fast, this is the gate), `langgraph`, `crewai`, `ag2`. Each installs only its own extra. A CrewAI nightly break then turns exactly one job red and the diagnosis is free.
- **Commit a lockfile** (`uv.lock` or `requirements/*.txt` compiled per extra) and run a separate scheduled `--upgrade` job so churn shows up as a dedicated failing cron job, not as a random red PR.
- **Pin to exact patch versions** in the lockfile, ranges in `pyproject.toml` (`crewai>=1.15,<2`, `langgraph>=1.2,<2`, `ag2>=1.1,<2`). Given CrewAI's daily dev releases, floating is not an option.
- **Declare the platform matrix in the README.** "Linux x86_64/arm64 and macOS arm64 supported; macOS x86_64 is not supported with the `crewai` extra due to an upstream `lancedb` wheel gap." Documented limitation beats a mystery install failure in a reviewer's terminal.

**Warning signs:**
- `pip install -e .` takes minutes, or downloads `onnxruntime`.
- `import eacp` fails when a framework is missing.
- A single CI job installs everything.
- Green PR yesterday, red PR today, no relevant diff.
- Your dependency tree contains `kubernetes` and you don't use Kubernetes.

**Phase to address:**
**Phase 1 (scaffold/packaging).** Extras, lazy imports, and the CI matrix are cheap on day 1 and a painful retrofit once three adapters and three examples have been written against a monolithic env.

---

### Pitfall 3: A "unified approval gate" that is really `input()` on two of three backends

**What goes wrong:**
The core value claim is "a single policy definition can govern a workflow regardless of which framework executes it — enforced for real." You implement the LangGraph gate with `interrupt()` + a checkpointer, which genuinely persists state and resumes in a different process. Then you implement CrewAI's with `human_input=True` and AutoGen's with `human_input_mode="ALWAYS"`, both of which are a blocking `input()` on the terminal. Now "pause the workflow, wait for approve/deny, resume or abort" means three completely different things: one durable pause, two blocked processes. A reviewer tries to approve a CrewAI run from a second terminal, discovers there's no run to approve — just a process sitting on stdin — and the unified-gate claim is dead.

**Why it happens:**
Each framework advertises "human in the loop" and the phrase papers over a categorical difference. Only LangGraph has a checkpointed, out-of-process, durable interrupt. CrewAI's `human_input=True` is documented as stdin-only and is widely reported as unusable for non-terminal workflows. AutoGen/AG2's `human_input_mode="ALWAYS"` blocks, and in async code blocks the entire event loop, freezing every other agent. The CLI-only scope in PROJECT.md hides the difference, because a CLI *looks* like a terminal prompt in all three cases.

**How to avoid:**
Invert the design. **The approval gate is a persisted record owned by the control plane; the framework hook is only the delivery mechanism.**
- Define `ApprovalRequest(run_id, node_or_task_id, payload, status: pending|approved|denied, requested_at, decided_at, decided_by)` in the run store. A gate fires by *writing a pending row and blocking on that row*, never by calling `input()`.
- The CLI is a **client of the store** (`eacp approvals list` / `eacp approve <id>`), not the mechanism. This is what makes the gate genuinely unified: the approve/deny surface is identical across all three backends because it never touches the framework.
- Per-framework delivery:
  - **LangGraph:** `interrupt()` + checkpointer. This is the only backend with true durable pause-and-resume via `Command(resume=...)` — use it, and say so.
  - **CrewAI:** do **not** use `human_input=True`. Use CrewAI 1.x's `before_tool_call` hook (returning `False` blocks tool execution and returns an error to the agent) and/or the LLM-call hooks, which the CrewAI docs explicitly list as suitable for implementing approval gates. Block inside the hook on the store row.
  - **AG2 / AutoGen Classic:** override the input function / intercept tool execution rather than relying on default stdin, and never block the event loop directly.
- **Publish a capability matrix** and make it machine-readable. Each adapter declares `capabilities: frozenset[str]`, e.g. `{"durable_pause", "per_tool_block", "per_agent_policy"}`. The policy validator then *fails loudly at registration time*: "policy `contract-review` requires `durable_pause`; adapter `crewai` does not provide it." Loud, early refusal is a feature; silent degradation to a lesser gate is the pitfall.

**Warning signs:**
- The word `input(` appears anywhere outside the CLI module.
- You cannot answer "which process is blocked, and what happens if it dies while awaiting approval?"
- There is no row in any table representing a pending approval.
- Approving requires the same terminal that started the run.
- The three adapters' approval code shares no types.

**Phase to address:**
**The approval-gate phase, and it must land *before* the three adapters.** The gate's data contract determines the adapter interface. Building adapters first guarantees three incompatible gate implementations that then have to be unified by rewrite.

---

### Pitfall 4: LangGraph's `interrupt()` re-runs the entire node, double-counting cost and duplicating side effects

**What goes wrong:**
You write one tidy `send_to_counterparty` node: call the LLM to draft the message, record token usage to the run store, append a trace span, then `interrupt()` for approval, then send. On resume, the LangGraph docs are explicit: *"the runtime restarts the entire node from the beginning — it does not resume from the exact line where `interrupt()` was called."* So the draft LLM call runs a second time, the token ledger is incremented twice, the trace gains a duplicate span, and the budget enforcement you were so careful about is now reporting 2× the real spend. If any pre-interrupt step had an external side effect (create a record, send a notification), it fires again — the docs warn that *"side effects called before `interrupt()` should (ideally) be idempotent."*

This pitfall is unusually dangerous for *this* project specifically, because cost accounting, audit tracing, and the approval gate are the three things EACP exists to do, and the naive implementation puts all three in the same node.

**How to avoid:**
- **The interrupt node contains only the interrupt.** Split into three nodes: `prepare` (LLM call, accounting) → `await_approval` (nothing but `interrupt()` and returning the decision) → `act` (the irreversible side effect). Post-approval side effects belong in a *subsequent node*, which the docs recommend directly.
- **Make the token ledger idempotent by construction.** Key every usage record on `(run_id, node_id, call_index)` and `UPSERT`, never `INSERT`. Then a replayed node is a no-op on the ledger regardless of how many times it re-executes. This is the one change that makes accounting correct under replay without reasoning about replay at every call site.
- **Never conditionally skip or non-deterministically loop `interrupt()` calls.** Resume-value matching is strictly index-based per node; a skipped interrupt misaligns every subsequent resume value. One interrupt per node sidesteps this entirely.
- Note the API shape: `Interrupt` now has exactly two fields (`value`, `id`). Code or docs referencing `resumable` / `ns` / `when` is pre-1.0 and wrong.
- **Write the regression test that catches this:** run a workflow to an approval, resume it, and assert the recorded token total and trace-span count are what a *single* pass would produce. Without this test the bug is invisible — everything still "works," the numbers are just wrong.

**Warning signs:**
- A node does work both before and after `interrupt()`.
- Token totals for approved runs are suspiciously round multiples of denied-run totals.
- Duplicate trace spans with different timestamps and identical content.
- Benchmark token counts for the LangGraph backend are ~2× the other two on an equivalent workflow (this will look like "LangGraph is expensive" and get published as a false finding — see Pitfall 9).
- The ledger uses `INSERT`.

**Phase to address:**
**LangGraph adapter phase**, with the idempotency-key design settled earlier in the cost/ledger phase.

---

### Pitfall 5: Enforcing the budget after the tokens are already spent

**What goes wrong:**
`max_tokens_per_run` and `max_cost_per_day` are checked in the `after_kickoff` hook, or the benchmark summary, or a `finally` block. The run completes, the check fires, the policy is marked violated — and the money is gone. A looping agent burns the daily budget in minutes and the control plane faithfully reports the overrun afterward. This is exactly the failure mode the literature calls out: guards that "measure cost after the fact or approximate it before, but do not block runaway agents in real time." A post-hoc check is a *report*, not a budget, and shipping it as enforcement directly contradicts this project's stated core value ("enforced for real, not just documented").

**Why it happens:**
Post-hoc is where the data is convenient — `crew.usage_metrics` after `kickoff()`, the final state after `.invoke()`. Pre-call enforcement requires interposing on every LLM call in three different frameworks, which is the hard part, so it gets deferred and then forgotten.

**How to avoid:**
Enforce at **three** points and be honest about the irreducible gap:
1. **Admission (pre-call, hard block).** Before each LLM call: `spent + estimate > limit` → raise/deny. Estimate input tokens with `tiktoken` (already a transitive dep) and treat `max_tokens` on the request as the output ceiling. This is where runaway loops actually die.
2. **Reconciliation (post-call).** Replace the estimate with the provider's reported usage, update the ledger, so the *next* admission check uses real numbers. Estimate for admission, actuals for accounting — never one for both.
3. **Step ceiling (structural).** `max_steps` / `max_iter` / max turns per run, enforced by the control plane independently of tokens. Token budgets fail open when usage reporting is broken (Pitfall 6); a step ceiling is a crude counter that cannot silently read zero. Keep both.

Then **document the bounded overshoot explicitly**: a single in-flight call cannot be cancelled mid-generation, so the worst case is one call's overshoot past the limit. Saying "we bound overshoot to one call" is credible engineering; claiming a hard cap you don't have is the pitfall.

Also: enforce per-run *and* per-day in the same ledger. `max_cost_per_day` with a process-local counter resets on every CLI invocation, making it decorative — it must live in the SQLite store, keyed by policy + UTC date.

**Warning signs:**
- The enforcement call site is in `after_*`, `finally`, or the reporting module.
- No code path raises *before* an LLM call.
- The daily counter is an in-memory attribute.
- There is no test asserting that an over-budget run stops *early* (assert the call count, not just the final status).
- `max_steps` doesn't exist.

**Phase to address:**
**Cost/policy-enforcement phase, before the adapters.** The adapters must be written against an interface that already has a pre-call admission hook; adding one later means touching all three.

---

### Pitfall 6: Token accounting silently reads zero, so the budget never trips

**What goes wrong:**
The budget code is correct, the tests pass, and no run ever exceeds its limit — because `usage_metadata` is `None` and you're summing zeros. This is a well-documented LangGraph/LangChain trap: usage metadata is dropped or nulled depending on `stream_mode` (lost with `stream_mode=["values","messages"]`, present with `["updates"]`), `astream_events(version="v3")` nulls `input_token_details`/`output_token_details`, `usage_metadata` returns `None` inside graphs in some configurations, and LiteLLM-backed wrappers omit usage entirely unless `stream_options` is set. Multiply by three frameworks with three different usage surfaces (LangChain `usage_metadata`, CrewAI `usage_metrics`, AG2's own accounting) and at least one of them will report nothing.

A budget on a zero counter looks *exactly* like a working budget that was never hit. This failure is completely silent and it invalidates the benchmark numbers too.

**How to avoid:**
- **Fail loud on missing usage.** Every recorded LLM call carries `usage_source: "provider" | "estimated" | "MISSING"`. If `MISSING`, log at WARNING and fall back to the `tiktoken` estimate — never to zero. A run containing any `MISSING` record is flagged in its trace and excluded from benchmark aggregates.
- **Assert non-zero in tests.** One test per adapter: execute a minimal workflow against the mock model and `assert recorded_tokens > 0`. This single assertion per backend is the highest-value test in the project.
- **Never let the mock model report zero usage.** The mock must emit plausible non-zero usage numbers (see Pitfall 11) or the entire enforcement test suite passes vacuously.
- **Pick one stream mode per adapter and pin it,** with a comment explaining that changing it drops usage data.
- Prefer a single-source ledger: get usage from the layer *you* control (a wrapper around the model client) rather than from each framework's reporting surface, where feasible. Three usage surfaces means three ways to silently read zero.

**Warning signs:**
- Zero policy violations ever observed in testing.
- Token totals of exactly `0`, or suspiciously identical across different workloads.
- Benchmark output where one backend reports dramatically fewer tokens than the others for equivalent work.
- Cost fields defaulting to `0.0` rather than `None`.

**Phase to address:**
**Observability/metrics phase**, with the `MISSING`-sentinel contract defined in the cost phase. The non-zero assertion goes into each adapter's phase exit criteria.

---

### Pitfall 7: Tool restrictions that live in the prompt instead of the execution path

**What goes wrong:**
`forbidden_tools: [send_email]` is implemented by omitting the tool from the list handed to the model and adding "you may not send email" to the system prompt. Both are advisory. The literature is blunt about this: prompt-level guardrails are bypassable because a model cannot reliably distinguish instructions from data, and a filtered tool list in the prompt while the real tool map remains intact is a documented bypass class (the tool stays reachable via a differently-shaped call, a sub-agent, an MCP passthrough, or a delegated task). CrewAI's task delegation and AG2's agent-to-agent handoff both create paths where an agent that "shouldn't have" a tool reaches one that does.

**Why it happens:**
Filtering the tool list is one line and demos convincingly — the agent visibly doesn't call the forbidden tool. It's indistinguishable from real enforcement until someone adversarial (or just an unusual input) tries.

**How to avoid:**
- **The control plane owns the tool registry.** Adapters never receive raw callables; they receive callables already wrapped by EACP. The policy check happens *inside the wrapper*, at invocation, so it fires no matter who calls it or how.
- **Use the per-framework execution-level hook, not the prompt:** CrewAI 1.x `before_tool_call` (returning `False` blocks execution and surfaces an error to the agent); LangGraph — wrap the tool callable / gate in the tool node; AG2 — intercept at tool execution registration.
- **Write the adversarial test, not the happy-path test.** Construct the forbidden tool call *directly in test code*, bypassing the model entirely, and assert it raises. A test where the model politely declines proves nothing about enforcement — it only proves the prompt worked that once.
- **Enforce on delegation edges too.** If an agent can hand work to another agent, the policy must apply to the *run*, not per-agent — otherwise `allowed_tools` per role is trivially escaped by asking a colleague. Check the effective policy at tool invocation against the run's policy, and treat per-role restrictions as a refinement layered on top, never as the only gate.
- Keep the prompt text *as well* (it reduces useless attempts and wasted tokens) but never *instead*.

**Warning signs:**
- `forbidden_tools` is only referenced where the tool list is built.
- No test calls a forbidden tool directly.
- Enforcement lives in the orchestration layer while tools execute somewhere else.
- The blocking mechanism differs per adapter in kind, not just in plumbing.
- Per-agent policy exists but per-run policy doesn't.

**Phase to address:**
**Tool-restriction phase**, with the wrapped-registry decision made in the core-engine phase (it's an interface decision).

---

### Pitfall 8: The lowest-common-denominator abstraction — and the specific form it takes here

**What goes wrong:**
The unified workflow abstraction can only express what all three frameworks share, so LangGraph's conditional edges and typed state, CrewAI's role/delegation model, and AG2's conversational turn-taking all flatten into a generic "steps" list. What you ship is strictly worse than any of the three underlying frameworks, and the honest reaction from a reviewer is "why would I not just use LangGraph directly?" The measured cost of over-abstraction in this ecosystem is real — roughly 42% of surveyed developers report deeply nested abstractions hindering work on non-standard requirements, and the abstractions leak: the moment behaviour is unexpected you're reading framework source anyway.

**The specific trap for this project** is `workflow.entrypoint` in the schema. There are two readings and only one survives:
- **Fatal reading:** the unified schema *describes the agent topology* — nodes, agents, roles, edges — in YAML, and each adapter compiles that YAML into a native graph/crew/conversation. This is the lowest-common-denominator trap in its purest form, it is a large amount of work, and it produces a worse version of all three frameworks.
- **Correct reading:** `entrypoint` is an opaque pointer to *native code the user wrote*. The user writes a real `StateGraph`, a real `Crew`, a real AG2 pattern, in that framework's idioms, using its full expressive power. EACP wraps it and governs it.

**How to avoid:**
- **Govern, don't define.** The unified layer's schema covers only what is genuinely universal: workflow identity, policy binding, cost ledger, approval records, trace format, run history. It says nothing about topology. This keeps the abstraction thin, honest, and — crucially — makes "add a fourth adapter" genuinely easy, which is a stated goal.
- **Make non-portability explicit and machine-readable.** Adapters declare `capabilities: frozenset[str]`; the policy validator refuses a registration whose policy needs a capability the adapter lacks. This converts "the abstraction is lossy" from a hidden flaw into a documented, enforced contract — and it is a far more credible engineering position than pretending the three frameworks are equivalent.
- **Publish the tradeoff in `DECISION_FRAMEWORK.md` as a first-class section,** not a footnote. A control plane that says "here is precisely what is portable, here is precisely what isn't, and here is why you'd still want one layer" is more adoptable than one claiming seamless portability. Platform teams have been burned by the latter and will trust the former.
- **Refuse abstraction with one implementation.** If a hook exists for exactly one adapter, it's not part of the unified interface — it's that adapter's business. Two real users before it's promoted to the core interface.

**Warning signs:**
- The YAML/JSON schema grows fields named `nodes`, `agents`, `edges`, `roles`, or `steps`.
- Users can't use a framework feature because the schema has no field for it.
- An adapter method exists that only one adapter implements meaningfully.
- The README claims "write once, run on any framework."
- A framework-specific concept (`Crew`, `StateGraph`, `ConversableAgent`) appears in a core module's type signature.

**Phase to address:**
**Core schema / engine phase (early).** This is the project's single highest-leverage architectural decision and the hardest to reverse — every example, doc, and adapter is written against it.

---

## Moderate Pitfalls

### Pitfall 9: A benchmark that measures your three implementations, not the three frameworks

**What goes wrong:** You run "the same logical workflow" on all three backends and publish a latency/token table. But you wrote three different implementations, with three prompt sets, three tool implementations, and three retry behaviours. The benchmarking literature names this precisely: the scaffold is a confounded variable, scores under different scaffolds are not comparable, and the harness often makes the execution-critical decisions the score is attributed to. A single-run table reading "CrewAI: 2.3× the tokens" gets screenshotted, and if Pitfall 4 is also present (LangGraph's double-counted replay) the published number is not merely noisy but wrong in a known direction.

**How to avoid:** Hold the model, prompts, tool implementations, and seed fixed — run the whole benchmark against the mock model by default so the numbers are deterministic and reproducible without keys. Run N≥5 and report median plus spread, never a single number. Title the output for what it actually measures: "control-plane overhead and orchestration cost for these three reference implementations," with the implementations linked. Publish step-count definitions per backend (a LangGraph "node" is not a CrewAI "task"). Add a methodology/limitations section stating the confound in plain language. A benchmark whose headline finding is "the control plane adds <Xms and 0 tokens of overhead" is defensible and genuinely useful; "framework A beats framework B" is not, from an N-of-1 harness written by one author.

**Phase to address:** Benchmark phase (late, after adapters are stable). Depends on Pitfall 4 and 6 being fixed first — benchmarking on a broken ledger produces confidently wrong published numbers.

---

### Pitfall 10: Demo-ware — examples that only work on the one scripted input

**What goes wrong:** Each example ships one sample input, on the approve path, and works beautifully. Change a word and the risk-analysis node produces something the recommendation node can't parse; deny the approval and the code path has never been executed. For a *governance* project this is fatal in a specific way: the deny path, the budget-exceeded path, and the forbidden-tool path **are the product**. A demo that only demonstrates approval demonstrates nothing about the control plane.

**How to avoid:** Every example ships at least three scripted scenarios, each an automated test as well as a CLI demo: (a) happy path, approved; (b) **approval denied** → assert the irreversible action did not happen; (c) a policy violation — budget exceeded, or forbidden tool attempted → assert the run halted with the violation recorded in its trace. The CLI grows a `--scenario` flag; the same three run in CI against the mock model. Do not aim for exhaustive input coverage — three named scenarios per example is enough, and resisting more is correct. Also assert on the *artifacts* (run status, trace contents, ledger totals), not on LLM prose, or the tests become flaky the moment the model changes.

**Phase to address:** Examples phase, with the scenario harness built once and reused across all three examples.

---

### Pitfall 11: A mock model too weak to exercise any enforcement path

**What goes wrong:** The no-API-key path returns a canned string. It never emits a tool call, so tool restrictions are never exercised; it reports zero usage, so budgets never trip; it never requests a gated action, so approvals never fire. CI is green and the entire control plane is untested. Combined with Pitfall 6 this produces a test suite that passes because every counter is zero.

**How to avoid:** Treat the mock as a real deliverable with its own phase budget, not a test fixture. It must: (a) emit **deterministic scripted tool calls**, including forbidden ones, so blocking is exercised; (b) report **plausible non-zero token usage** so budgets are exercised; (c) support a runaway mode (keeps calling tools) so the step ceiling and pre-call admission are exercised. Note the real cost honestly: it has to satisfy three different model interfaces (a LangChain `BaseChatModel`, whatever CrewAI's LLM layer expects, and AG2's client protocol), so this is three shims, not one — and it's a plausible candidate for its own phase. `langchain-core` ships fake chat models that are a reasonable base for the LangGraph side; the other two need hand-written shims.

**Phase to address:** Immediately before or alongside the first adapter. Every subsequent phase's tests depend on it, which also makes it a natural early phase.

---

### Pitfall 12: The workflow registry loads arbitrary Python from YAML

**What goes wrong:** `entrypoint: "my.module:build_graph"` in a YAML file, resolved with `importlib`. The registry is now an arbitrary-code-execution primitive driven by a config file — and the project's framing invites users to treat workflow/policy YAML as declarative, reviewable data (they'll put it in a shared repo, generate it, accept it from a PR). Compounding it: `yaml.load` instead of `yaml.safe_load` is RCE on the policy file itself.

**How to avoid:** `yaml.safe_load`, always — no exceptions. Restrict entrypoint resolution to an explicit allowlist of module prefixes, or better, require registration through a decorator/entry-point group in Python so the YAML references a *registered name* rather than an import path. Document loudly that workflow YAML is trusted input equivalent to source code. Reject `entrypoint` values containing path separators or `..`.

**Phase to address:** Core engine / registry phase.

---

## Minor Pitfalls

### Pitfall 13: Traces become the compliance leak

Prompts and tool arguments in a contract-review or incident-response workflow contain exactly the data `compliance_tags: [PII, legal]` exists to mark. Writing full payloads to a SQLite file with default permissions, unredacted, is a governance project leaking governed data. Redact or hash payloads by default with opt-in verbose capture, store a content hash for audit, and honour `compliance_tags` in the trace writer — the tags should *do something*, otherwise they're decoration. **Phase:** observability.

### Pitfall 14: Synchronous per-event writes to SQLite in the hot path

A `commit()` per trace span and per token record makes the control plane the slowest part of the run — and then you publish latency benchmarks that measure your own `fsync`. Batch spans per node, write once per node boundary, WAL mode. Only matters above ~hundreds of events per run, which the benchmark runner will reach. **Phase:** observability / benchmark.

### Pitfall 15: Approval fatigue and contextless prompts

`required_approval_nodes` applied liberally produces a CLI that asks for approval constantly, and humans rubber-stamp. Worse, a prompt reading `Approve node 'send_to_counterparty'? [y/N]` gives the approver nothing to decide on. Gate only irreversible/external actions; render the actual payload, the policy that triggered the gate, and the run's cost-so-far in the prompt; make the default deny; record `decided_by` and the rationale. **Phase:** approval-gate / CLI.

### Pitfall 16: Documenting a decision framework without running it

`DECISION_FRAMEWORK.md` written from general impressions of the three frameworks reads like every other comparison blog post. Write it *after* building all three adapters, from what actually hurt — where each framework's hooks were missing, what the capability matrix ended up excluding, what the benchmark showed. This file plus the "AutoGen naming situation" section are the two pieces most likely to earn the project genuine attention. **Phase:** docs phase, last.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|---|---|---|---|
| All three frameworks as hard dependencies | One `pip install`, no extras plumbing | 155-package env; unresolvable on macOS x86_64; `import eacp` requires all three; one CI job that any upstream nightly can redden | **Never** — extras cost ~20 lines on day 1 |
| Post-hoc budget check (`after_kickoff`) | Usage data is right there | Contradicts the project's core value claim; a reviewer will find it in five minutes | **Never** — this *is* the product |
| Prompt-level / tool-list-filtering restriction | One line, demos convincingly | Bypassable by delegation, sub-agents, differently-shaped calls; indistinguishable from enforcement until adversarially tested | As a *supplement* to execution-level blocking, never as the mechanism |
| `human_input=True` / `human_input_mode="ALWAYS"` for the gate | Works instantly in a terminal | Not a pause — a blocked process; no cross-process approval; makes the "unified gate" claim false | Never for the gate. Fine as a documented "native HITL, for comparison" appendix |
| Topology (`nodes`/`agents`/`edges`) in the unified YAML schema | Looks impressively declarative | Lowest-common-denominator trap; reimplements three frameworks worse; every framework upgrade breaks the compiler | Never |
| One sample input per example | Ships the demo fast | Deny/violation paths — the actual product — never execute | Never; three scenarios is the floor |
| Trace spans committed one-per-event | Simple, obviously correct | Control plane dominates measured latency; benchmark measures your `fsync` | Acceptable pre-benchmark; fix before publishing numbers |
| Floating framework versions | Always current | CrewAI publishes a nightly *daily*; random red PRs, unreproducible benchmarks | Never — lockfile + scheduled upgrade job instead |
| Mock model returns a canned string | Unblocks CI immediately | Vacuous test suite: zero tool calls, zero tokens, zero enforcement exercised | Only for the first scaffold commit; must be replaced before any enforcement phase exits |
| Module named `autogen_adapter.py` | Matches how everyone says it | Ambiguous across four packages; readers cannot tell what you built | Never — name it for the package |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|---|---|---|
| "AutoGen" | Treating `autogen` / `pyautogen` / `autogen-agentchat` / `ag2` as one thing | Four distinct codebases. `autogen-agentchat` = Microsoft, maintenance mode, ~12mo stale. `autogen` = AG2 Classic (`import autogen`). `ag2` = AG2 mainline (`import ag2`, not drop-in from Classic). `pyautogen` = stale proxy to Microsoft's. Pick one, pin it, name the module after it. |
| `autogen-agentchat` | Upgrading `agentchat` without `core`/`ext` | It pins `autogen-core==0.7.5` exactly. Upgrade the trio atomically. Also drags the env's `protobuf` down to 5.29.x. |
| CrewAI | Installing on Intel macOS; assuming 0.x docs apply | `lancedb>=0.29.2,<0.30.1` has no macOS x86_64 wheel → unresolvable. `requires_python <3.14`. 1.x changed `kickoff()` to return `dict` and requires `BaseTool`/typed `@tool`. |
| CrewAI hooks | Reaching for `human_input=True` | Use 1.x execution hooks: `before_tool_call` (return `False` to block), LLM-call hooks (documented for approval gates), `usage_metrics` for tokens. These are 1.x-only — another reason to pin 1.x. |
| LangGraph | Work before and after `interrupt()` in one node | Node replays from the top on resume. Interrupt-only node; side effects in the next node; idempotent (upsert) accounting. |
| LangGraph | Copying pre-1.0 `Interrupt(resumable=…, ns=…, when=…)` | `Interrupt` is now `value` + `id` only. Resume via `Command(resume=…)`. |
| LangGraph token usage | Trusting `usage_metadata` to be present | Nulled/dropped depending on `stream_mode` and `astream_events` version; LiteLLM wrappers omit it without `stream_options`. Pin one stream mode; record `usage_source`; never default to 0. |
| `langchain-core` | Forgetting `langgraph` constrains it (`>=1.4.7,<2`) | Pin `langchain-core` in the lock; an independent bump can break the LangGraph adapter with no diff of yours. |
| SQLite run store | One connection shared across threads/async; per-event commit | WAL mode, connection-per-thread, batch writes at node boundaries. Keep the store interface narrow so Postgres stays a drop-in. |
| Mock/local model | One mock assumed to satisfy all three | Three model interfaces → three shims. `langchain-core`'s fake chat models cover the LangGraph side only. |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|---|---|---|---|
| Per-event SQLite commit | Control-plane overhead dominates benchmark latency | Batch per node boundary; WAL | ~hundreds of events/run — reachable by the benchmark runner |
| Full prompt/response payloads in every trace row | DB grows tens of MB per benchmark sweep; slow queries | Store hashes + truncated previews by default; verbose opt-in | A few hundred runs |
| Installing all extras in CI | Multi-minute installs on every PR; flaky wheel fetches | Per-adapter CI jobs; cached lockfile-keyed venvs | Immediately (155 packages) |
| Benchmark against live APIs | Slow, costs money, non-deterministic, unrunnable by reviewers | Mock model is the default benchmark target; live is opt-in | First benchmark run |
| Node replay from `interrupt()` doubling work | Approved runs cost ~2× denied runs | Interrupt-only nodes (Pitfall 4) | Any run with an approval — i.e. all of them |
| Unbounded agent loop | Runaway cost, hung CLI | Pre-call admission + `max_steps` ceiling | Any run where the model misbehaves once |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---|---|---|
| `entrypoint` module path resolved from YAML | Arbitrary code execution via a config file that users treat as declarative data | Registry/decorator-based names, or an explicit module-prefix allowlist; reject separators and `..`; document YAML as trusted input |
| `yaml.load` instead of `yaml.safe_load` | RCE via the policy file | `safe_load` unconditionally |
| Restrictions enforced in prompts / filtered tool lists | Bypass via delegation, sub-agents, differently-shaped calls; "governance" that doesn't govern | Wrap the tool callable; enforce at invocation; test by calling the forbidden tool directly |
| Per-role `allowed_tools` with no run-level check | Agent A asks agent B to do the forbidden thing | Effective policy resolved at invocation against the *run's* policy; per-role is a refinement, not the gate |
| Full prompts/outputs in traces under `compliance_tags: [PII]` | The governance tool is the exfiltration path; file-permission and retention exposure | Redact/hash by default; make `compliance_tags` actually drive the trace writer; restrictive file mode on the SQLite file |
| Approval decisions not bound to the specific request | Replay/confusion: a stale approval authorises a different action | Approval row keyed by `(run_id, node_id, payload_hash)`; a payload change invalidates the approval |
| Mutable audit trail | Post-hoc editing of who approved what defeats the audit purpose | Append-only decision records; never `UPDATE` a decided approval; record `decided_by` and timestamp |
| Provider keys read at import time / echoed into traces | Key leakage into run history and logs | Read lazily at call time; never persist request headers; explicit denylist in the trace serialiser |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---|---|---|
| `Approve 'send_to_counterparty'? [y/N]` with no payload | Approver has nothing to decide on; rubber-stamps | Render the actual payload, the triggering policy rule, and cost-so-far; default deny |
| Approval requires the terminal that started the run | Not a control plane; unusable for anything scheduled | Approvals are store rows; CLI is a client (`approvals list` / `approve <id>`) |
| Too many gated nodes | Approval fatigue → reflexive approval → gate is theatre | Gate irreversible/external actions only; make gating a deliberate, documented choice per example |
| Policy violation surfaces as a raw traceback | User can't tell a violation from a bug | Typed `PolicyViolation` with rule id, limit, observed value, run id; non-zero exit; recorded in the trace |
| Silent degradation when an adapter lacks a capability | User believes a policy is enforced when it isn't — the worst possible failure for this project | Capability matrix + validation error at registration time: "policy requires `durable_pause`; adapter `crewai` lacks it" |
| Quickstart that needs an API key | Reviewers bounce at step one | Mock model is the documented default; the very first command in the README runs with no key |
| Install instructions that omit extras | `import eacp` → `ModuleNotFoundError: crewai` | `pip install eacp[langgraph]` etc. front and centre, with the platform support matrix next to it |

---

## "Looks Done But Isn't" Checklist

- [ ] **Budget enforcement:** often only post-hoc — verify a test asserts the run stopped **early** by counting LLM calls, not just that status is `failed`.
- [ ] **Token accounting:** often silently zero — verify `assert tokens > 0` exists per adapter, and that `usage_source == "MISSING"` is logged and never coerced to 0.
- [ ] **Daily cost cap:** often a process-local counter — verify it survives a fresh CLI invocation (two runs in separate processes, second one denied).
- [ ] **Tool restriction:** often prompt-only — verify a test invokes the forbidden tool **directly**, bypassing the model, and it raises.
- [ ] **Delegation:** verify an agent can't reach a forbidden tool via another agent/task.
- [ ] **Approval gate:** often blocking `input()` — verify approve/deny works from a **second process** with the first still pending, and that a pending approval survives killing the runner (LangGraph) or is explicitly documented as not surviving (others).
- [ ] **Denied approval:** verify the irreversible action **did not execute** and the run's terminal status is `denied`, not `completed`.
- [ ] **LangGraph replay:** verify token totals and trace-span counts after an approve-resume match a single pass (no doubling).
- [ ] **Core-only install:** verify `pip install eacp && python -c "import eacp"` succeeds with **zero** agent frameworks present, and that the policy engine's tests pass in that env.
- [ ] **Capability mismatch:** verify registering a `durable_pause`-requiring policy on the CrewAI adapter **fails at registration**, loudly.
- [ ] **Mock model:** verify it emits tool calls and non-zero usage on all three backends — otherwise every enforcement test above is vacuous.
- [ ] **Examples:** verify all three scenarios (approve / deny / violation) run in CI with no API key, for each of the three examples.
- [ ] **Benchmark:** verify it runs keyless, reports N runs with spread, and its limitations section names the scaffold confound.
- [ ] **Adapter naming:** verify no module, doc, or heading says bare "AutoGen" where it means a specific package.
- [ ] **Docs:** verify `DECISION_FRAMEWORK.md` contains the capability matrix and the AutoGen-naming section, and was written after the adapters.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---|---|---|
| Wrong AutoGen package chosen (1) | **MEDIUM→HIGH** | Rewrite one adapter + one example + one tutorial. Cheap in Phase 1, expensive after the benchmark and docs are written against it. Mitigation: decide in Phase 1. |
| Monolithic dependencies (2) | MEDIUM | Split into extras, move imports into adapter bodies, split the CI job, compile per-extra locks. Mechanical but touches packaging, CI, and docs. |
| `input()`-based approval gate (3) | **HIGH** | Redesign the gate as store rows; rewrite all three adapters' gate paths and the CLI. This is the rewrite Pitfall 3 exists to prevent. |
| LangGraph node-replay double counting (4) | LOW | Split the node in three; switch the ledger to upsert on `(run_id, node_id, call_index)`. Small diff — but any published benchmark numbers must be regenerated. |
| Post-hoc budget enforcement (5) | MEDIUM | Add a pre-call admission hook to the adapter interface and thread it through all three adapters. Cheap if the interface already has the hook; a three-adapter change if not. |
| Silent zero token accounting (6) | LOW | Add `usage_source`, the `MISSING` sentinel, and per-adapter non-zero assertions. But all prior benchmark and policy results are invalid and must be rerun. |
| Prompt-only tool restriction (7) | MEDIUM | Move blocking into wrapped callables; re-verify per framework; add adversarial tests. |
| Lowest-common-denominator schema (8) | **HIGH** | Deleting a topology-compiling schema invalidates every example, tutorial, and adapter written against it. Effectively a restart of the core. Prevent in the schema phase. |
| Confounded benchmark published (9) | MEDIUM (reputational) | Retract/annotate the numbers, add methodology + limitations, rerun with fixed model/prompts/tools and N≥5. Costly because it's public. |
| Demo-ware examples (10) | LOW | Add deny + violation scenarios per example. Small diff, high credibility gain — and it usually surfaces real bugs in the enforcement paths. |
| Too-weak mock model (11) | MEDIUM | Rebuild the mock with scripted tool calls and usage; then re-verify every enforcement test that was previously passing vacuously. |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---|---|---|
| 1. Wrong/ambiguous AutoGen package | **Phase 1 — stack decision (blocking)** | Adapter module is named for the package; exact pin in lock; decision + rejected alternatives recorded |
| 2. Monolithic dependency environment | **Phase 1 — scaffold/packaging** | `import eacp` succeeds with zero frameworks; 4 CI jobs; per-extra locks committed; platform matrix in README |
| 8. Lowest-common-denominator schema | **Phase 1–2 — core schema/engine** | Schema has no topology fields; `capabilities` declared per adapter; mismatched policy fails at registration |
| 12. YAML → arbitrary code execution | Phase 2 — registry | `safe_load` only; entrypoint allowlist; malicious-entrypoint test rejected |
| 5. Post-hoc budget enforcement | **Phase 2–3 — policy/cost engine (before adapters)** | Over-budget run stops early, asserted by LLM-call count; `max_steps` exists; daily cap persists across processes |
| 6. Silently zero token accounting | Phase 2–3 — cost contract; enforced in observability | `usage_source` field present; `assert tokens > 0` per adapter; `MISSING` logged, never 0 |
| 3. Approval gate as `input()` | **Phase 3 — approval gate (before adapters)** | Approve/deny from a second process; `ApprovalRequest` rows exist; no `input(` outside the CLI |
| 11. Too-weak mock model | Phase 3–4 — alongside the first adapter | Mock emits tool calls + non-zero usage on all three backends |
| 7. Prompt-only tool restriction | Phase 4 — tool restriction / adapters | Direct forbidden-tool invocation raises; delegation path also blocked |
| 4. LangGraph node replay | Phase 4 — LangGraph adapter | Post-resume token/span counts equal a single pass; ledger uses upsert |
| 13. Traces leak governed data | Phase 5 — observability | `compliance_tags` change trace output; payloads hashed/redacted by default |
| 14. Per-event SQLite commits | Phase 5 — observability | WAL on; writes batched per node; overhead measured and reported |
| 15. Approval fatigue / contextless prompts | Phase 5 — CLI/UX | Prompt shows payload + rule + cost; default deny; `decided_by` recorded |
| 10. Demo-ware examples | Phase 6 — examples | Three scenarios per example (approve/deny/violation), all keyless in CI |
| 9. Confounded benchmark | Phase 7 — benchmarks | Fixed model/prompts/tools; N≥5 with spread; limitations section names the confound |
| 16. Unearned decision framework | Phase 8 — docs (last) | Capability matrix + AutoGen-naming section present, written post-adapters |

---

## Sources

**Verified locally (HIGH confidence — empirical, reproducible 2026-09-24):**
- PyPI JSON metadata for `langgraph` (1.2.12), `crewai` (1.15.22), `autogen` (0.14.1 → `github.com/ag2ai/ag2classic`), `ag2` (1.1.0 → `github.com/ag2ai/ag2`), `autogen-agentchat` / `autogen-core` / `autogen-ext` (0.7.5, last stable 2025-09-30), `pyautogen` (0.10.0, proxies `autogen-agentchat`) — versions, `requires_python`, `requires_dist`, release timelines
- Wheel inspection: `ag2-1.1.0` top-level package is `ag2`; `autogen-0.14.1` top-level package is `autogen`
- `uv pip compile` resolutions: per-framework transitive counts (38 / 134 / 22 / 14 / 11); combined 155; hard resolution failure on `macosx_*_x86_64` via `crewai → lancedb>=0.29.2,<0.30.1`; `protobuf` pull-down 7.36.2 → 5.29.6 when `autogen-core` is present

**Official documentation (HIGH confidence):**
- `github.com/microsoft/autogen` README — "AutoGen is now in maintenance mode… New users should start with Microsoft Agent Framework"
- LangChain docs, LangGraph Interrupts — node replays from the beginning on resume; side effects before `interrupt()` should be idempotent; index-based resume matching; don't conditionally skip or non-deterministically loop interrupts
- `devblogs.microsoft.com/agent-framework` — Agent Framework as successor to Semantic Kernel + AutoGen; `pip install agent-framework`
- CrewAI docs — Execution Hooks / Tool Call Hooks (`before_tool_call` returning `False` blocks execution), LLM Call Hooks (documented for approval gates), `usage_metrics`; Human-in-the-Loop (`human_input=True` is stdin-based)
- `ag2ai/ag2` releases — v1.0 import namespace change to `ag2`; Classic moved to `ag2ai/ag2-classic`; "not a drop-in upgrade"

**Community issues / reports (MEDIUM confidence, multiple corroborating sources):**
- `langchain-ai/langgraph` issues #8094, #4848, #5951, #3936 — `usage_metadata` dropped or `None` depending on `stream_mode` / `astream_events` version
- LiteLLM wrapper omits cached/streamed usage without `stream_options`
- `crewAIInc/crewAI` issue #2051 and CrewAI community threads — `human_input` is stdin-only, unusable for async/backend workflows
- AutoGen HITL docs + community reports — `human_input_mode="ALWAYS"` blocks; direct `input()` blocks the asyncio event loop, freezing all agents
- CrewAI 0.x→1.x migration notes — `kickoff()` returns `dict`; `BaseTool`/typed `@tool` required; pin exact microversions
- Agent guardrail bypass reports (e.g. `allowedTools` restriction advertised in prompt but not enforced in the runtime tool map) — prompt-level restriction is not enforcement

**Academic / analytical (MEDIUM confidence):**
- "The Double Measurement Confound in Agent Benchmarks" — scaffold as a confounded variable; scores under different scaffolds are not comparable
- "Benchmarking Crimes" — unfair-competitor-configuration class of error
- "Token Budgets: An Empirical Catalog of LLM-Agent Budget-Overrun Incidents" and related — post-hoc guards admit at least one overshooting call; usage known only after completion; multi-call protection is the achievable guarantee
- "An Empirical Study of Agent Developer Practices in AI Agent Frameworks" — ~42% of developers report deeply nested abstractions hindering non-standard work; leaky abstractions force reading framework source

---
*Pitfalls research for: vendor-agnostic multi-framework agent control plane (LangGraph / CrewAI / AutoGen)*
*Researched: 2026-09-24*
