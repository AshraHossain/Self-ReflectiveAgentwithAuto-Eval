# Stack Research

**Domain:** Vendor-agnostic control plane / governance layer over Python multi-agent frameworks (LangGraph, CrewAI, AutoGen)
**Researched:** 2026-09-24
**Confidence:** HIGH (versions, hook surfaces and co-installability verified against PyPI metadata, published wheel source, and a real `uv` dependency resolution — not training data)

---

## TL;DR — The One Thing That Changed

**The AutoGen ecosystem has fractured three ways since early 2025. Training-data knowledge here is stale and will produce a broken adapter.** Verified state as of 2026-09-24:

| Package | Latest | Last release | Verdict |
|---------|--------|--------------|---------|
| `ag2` | **1.1.0** | **2026-09-24 (today)** | ✅ **USE THIS.** Actively maintained mainline. Imports as `ag2`. |
| `autogen` | 0.14.1 | 2026-06-30 | ⚠️ "AG2 Classic", maintenance mode. Imports as `autogen`. Fallback only. |
| `autogen-agentchat` / `-core` / `-ext` | 0.7.5 | 2025-09-30 | ❌ Microsoft's line. ~1 year stale, maintenance mode. |
| `pyautogen` | 0.10.0 | 2025-07-15 | ❌ Dead proxy shim to `autogen-agentchat`. |
| `agent-framework` | 1.19.0 | 2026-09-18 | ❌ Microsoft's *successor* to AutoGen. Actively developed but a different framework, out of spec. |

Two independent things happened:

1. **Microsoft folded AutoGen into Semantic Kernel** and shipped the merger as **Microsoft Agent Framework** (Oct 2025). `autogen-agentchat` is in maintenance mode — security patches only. Microsoft publishes an official AutoGen → Agent Framework migration guide.
2. **AG2 (the community fork that kept the AutoGen name and API) shipped v1.0 in July 2026 as a full rewrite.** The classic `ConversableAgent` / `GroupChat` / `register_hook` API was **removed from the mainline repo** and relocated to `ag2ai/ag2-classic` (docs at `classic.docs.ag2.ai`), distributed as the `autogen` PyPI name. The new `ag2` package has a different import namespace and a completely different API.

**Verified by inspecting the actual wheels**, not docs prose:

- `ag2-1.1.0-py3-none-any.whl` → single top-level package `ag2/`. **No** `ConversableAgent`, **no** `register_hook` anywhere in 444 source files. Exports `Agent`, `Task`, `Middleware`, `observer`, `Plugin`, `Toolkit`.
- `autogen-0.14.1-py3-none-any.whl` → top-level `autogen/`. `register_hook` defined in `autogen/agentchat/conversable_agent.py`; `GroupChat` in `autogen/agentchat/groupchat.py`.

**There is no `ag2-classic` package on PyPI** — that's a repo name, not a distribution. A web result claiming otherwise was wrong; the install name for classic is `autogen`.

### Recommendation: `ag2>=1.1,<2`

Not just because it's maintained — because **ag2 1.x's architecture is a near-exact match for what EACP needs**, which flips the AutoGen adapter from the hardest to arguably the easiest of the three. Verified from `ag2/agent.py`, the `Agent` constructor accepts these directly:

```python
Agent(
    name: str,
    prompt: ...,
    *,
    config: ModelConfig | None = ...,
    hitl_hook: HumanHook | None = ...,        # ← human-in-the-loop seam
    tools: ... = ...,
    middleware: Iterable[MiddlewareFactory] = ...,   # ← policy seam
    observers: Iterable[Observer] = ...,             # ← tracing seam
    plugins: ... = ...,
)
```

Accept the tradeoff honestly: the new API has ~2 months of community material behind it and most tutorials/StackOverflow answers you'll find describe the classic API. Budget real time for reading `ag2` source. It is a young API surface on a fast release cadence (0.13.1 → 1.1.0 in four months), so pin tightly and expect churn.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Python** | `>=3.11,<3.14` | Runtime | `crewai` hard-caps `<3.14`; it is the binding constraint. Target **3.12** for dev/CI — widely packaged, and avoids 3.13 edge cases in the heavy native deps (`onnxruntime`, `pyarrow`) CrewAI drags in. |
| **langgraph** | `1.2.12` (`>=1.2,<1.3`) | LangGraph backend | Graph runtime with the best HITL primitive of the three: `interrupt()` + `Command(resume=...)` + durable checkpointers. Verified current in Context7 docs. |
| **langchain** | `1.4.2` (`>=1.4,<2`) | Agent middleware + `create_agent` | Only needed if you use `create_agent`/middleware rather than raw `StateGraph`. Pins `langgraph>=1.2.11,<1.3.0` — compatible with the above by construction. |
| **langchain-core** | `1.6.5` (`>=1.6,<2`) | Message types + **fake chat models** | Transitive via langgraph, but declare it: you depend directly on `langchain_core.language_models.fake_chat_models` for key-free runs. |
| **langgraph-checkpoint-sqlite** | `3.1.1` (`>=3.1`) | Durable checkpointer | `SqliteSaver` from `langgraph.checkpoint.sqlite`. Required for approval-gate pause/resume to survive process exit. Not optional for the HITL requirement. |
| **crewai** | `1.15.22` (`>=1.15,<2`) | CrewAI backend | v1.x ships a first-class `crewai.hooks` package (see below) — a huge improvement over the old `step_callback` era. **Heaviest dependency by far (134 packages).** |
| **ag2** | `1.1.0` (`>=1.1,<2`) | AutoGen-lineage backend | Actively maintained line; native middleware/observer/HITL seams; only 14 transitive packages. |
| **pydantic** | `2.12.5` (`>=2.11,<2.13`) | Policy + workflow schema validation | **The `<2.13` cap is forced by `crewai-core`, not a preference.** See Version Compatibility. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **typer** | `0.27.2` (`>=0.27`) | CLI per example | Already transitive (via `chromadb`, `instructor`) — **zero added dependency cost**. Type-hint-driven, matches the project's typed style. |
| **PyYAML** | `6.0.3` (`>=6`) | Load policy/workflow YAML | Already transitive via all three frameworks. Use `yaml.safe_load` only. |
| **opentelemetry-sdk** + **opentelemetry-api** | `1.44.0` (`>=1.42,<2`) | Tracing + metrics | **Already a hard core dependency of `crewai-core`.** Declining OTel does not make it go away — it only means you ship a second, worse tracing system alongside it. |
| **sqlite3** | stdlib | Run-history store | See the store decision below. No dependency. |
| **csv** / **json** | stdlib | Benchmark output | See benchmark decision below. No dependency. |

### Development Tools

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| **uv** | `0.12.19` | Dep management, lockfile, venvs | The 2026 default. Critical here: it resolves this 156-package graph in seconds and produces a `uv.lock` that makes your benchmark numbers reproducible. CrewAI itself now vendors `uv` as a dependency. |
| **pytest** | `9.1.1` | Test runner | Use markers to isolate framework-heavy tests (below). |
| **pytest-asyncio** | `1.4.0` | Async tests | Mandatory: `ag2` middleware hooks are `async def` throughout. Set `asyncio_mode = "auto"`. |
| **ruff** | `0.16.9` | Lint + format | Replaces black+isort+flake8. One tool, one config block. |
| **mypy** | `2.3.1` | Type checking | The spec demands type hints; a typed adapter interface is the project's core abstraction, so check it. Expect to need `ignore_missing_imports` for the heavy frameworks. |

---

## How Each Framework Exposes Policy / Tracing / Interrupt Hooks

This is the load-bearing research for the adapter design. All three have *real* interception seams — **no monkey-patching is required for any of them.** That was not true 18 months ago.

### LangGraph 1.2 — the best interrupt story

**Interrupt / HITL (approval gates):** `interrupt()` inside a node pauses the graph and persists state; resume with `Command(resume=value)` on the same `thread_id`.

```python
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

graph = builder.compile(checkpointer=SqliteSaver(sqlite3.connect("cp.db")))
config = {"configurable": {"thread_id": "run-1"}}

graph.invoke(initial_state, config)          # runs until interrupt() → returns
graph.invoke(Command(resume="approved"), config)   # resumes
graph.invoke(None, config)                   # resume a drained run without new input
```

**Policy enforcement:** three options, in ascending order of laziness:
- Wrap node callables in the adapter before `add_node` — simplest, works with raw `StateGraph`.
- `error_handler=` on `add_node` returning a `Command(goto=...)` to route a policy violation to a deny/compensate node instead of crashing the run. Verified current in LangGraph 1.2 fault-tolerance docs.
- If you use `langchain.create_agent`, use LangChain's agent middleware (`wrap_tool_call`, `before_model`, plus a built-in `HumanInTheLoopMiddleware`).

**Tracing:** read the checkpoint history — `graph.get_state_history(config)` gives `StateSnapshot`s with `.metadata["step"]`, `.next`, and `.tasks[*].interrupts`. You get a per-node trace and approval detection for free from the checkpointer you already need. Confirmed pattern in official docs:

```python
interrupted = next(s for s in history if s.tasks and any(t.interrupts for t in s.tasks))
```

**Confidence: HIGH** (Context7 `/websites/langchain_oss_python_langgraph`, current docs).

### CrewAI 1.15 — a real hooks package, plus native deny

Verified by reading `crewai/hooks/__init__.py` in the 1.15.22 wheel. Public API:

```python
from crewai.hooks import (
    before_tool_call, after_tool_call,       # decorators
    before_llm_call, after_llm_call,
    register_before_tool_call_hook,           # imperative registration
    ToolCallHookContext, LLMCallHookContext,
    HookAborted,                              # ← raise to block
    InterceptionPoint, on, register_hook, dispatch,
    clear_all_global_hooks,                   # ← essential for test isolation
)
```

- **Tool restriction:** `before_tool_call` hook + raise `HookAborted`. `ToolCallHookContext` carries `tool_name`, mutable `tool_input`, `tool`, `agent`, `task`, `crew` — enough for *per-role* policy, which the sales-intelligence example requires.
  - Gotcha straight from the docstring: mutate `context.tool_input` **in place**. Reassigning the dict silently does nothing.
- **Cost/rate limits:** `before_llm_call` hook. `crewai/llms/base_llm.py` defines `LLMCallBlockedError` and `get_token_usage_summary()` — CrewAI natively supports hooks denying an LLM call and tracks token usage per LLM instance. You do not need to build token accounting here.
- **Generic interception points** (`InterceptionPoint` enum, verified): `EXECUTION_START`, `INPUT`, `OUTPUT`, `EXECUTION_END`, `PRE_MODEL_CALL`, `POST_MODEL_CALL`, `PRE_TOOL_CALL`, `POST_TOOL_CALL`, `PRE_STEP`, `POST_STEP`.
- **Tracing:** an event bus at `crewai.events` with ~20 typed event modules (`tool_usage_events`, `llm_events`, `task_events`, `crew_events`, `checkpoint_events`). Subclass `BaseEventListener` — do **not** use `step_callback` for tracing, the event bus is strictly richer.
- **HITL:** `Task(human_input=True)` for the built-in loop, but the real seam is the `HumanInputProvider` **Protocol** in `crewai/core/providers/human_input.py` (`runtime_checkable`, ContextVar-scoped). Implement it to route CrewAI approvals through EACP's central gate instead of `input()`.
- **Pause/resume:** CrewAI 1.15 has checkpointing — `crewai/state/provider/sqlite_provider.py` plus `CheckpointRestoreStartedEvent` / `CheckpointForkStartedEvent`. Worth evaluating before hand-rolling resume for the CrewAI backend.

**Confidence: HIGH** (read directly from published wheel source).

### ag2 1.1 — middleware designed for exactly this

Verified from `ag2/middleware/base.py`. `BaseMiddleware` is an ASGI-style `call_next` chain:

```python
class BaseMiddleware:
    async def on_turn(self, call_next, event, context) -> ModelResponse: ...
    async def on_llm_call(self, call_next, events, context) -> ModelResponse: ...
    async def on_tool_execution(self, call_next, event: ToolCallEvent, context) -> ToolResultType: ...
```

Register per-agent via `Agent(middleware=[...], observers=[...], hitl_hook=...)`.

Built-ins already shipped in `ag2.middleware.builtin` (verified present):

| Built-in | Maps to EACP requirement |
|----------|--------------------------|
| `ApprovalRequired` / `approval_required` | Human approval before a tool call — *the incident-response example's core requirement* |
| `TokenLimiter` | Token budget enforcement |
| `RetryMiddleware` | Resilience |
| `LoggingMiddleware` | Run logging |
| `TelemetryMiddleware` | OpenTelemetry (needs `ag2[tracing]`) |
| `MetricsMiddleware` | Prometheus (needs `ag2[metrics]`) |

`ApprovalRequired` is a clean reference implementation to mirror: it's a plain callable satisfying `ToolMiddleware`, calls `await context.input(...)`, stores "always approve" state in `context.variables` under a namespaced key, and supports `timeout`. Read it before designing EACP's gate.

- **Blocking a tool:** just don't call `call_next` in `on_tool_execution` — return a `ToolErrorEvent`. No exceptions needed.
- **Tracing:** `ag2.observers` — `observer(ModelResponse, on_response)` for lightweight `condition → callback` subscriptions, or subclass `BaseObserver` for stateful monitors. Ships `TokenMonitor` and `LoopDetector`.
- **Multi-agent conversation:** `ag2.network` — `adapters/conversation.py`, `adapters/discussion.py`, `adapters/consulting.py`, `adapters/workflow.py`, plus `handoff.py`, `hub/arbiter.py`, `hub/audit.py`, and `network/policies.py`. The incident-response (detector/triage/communicator) example is expressible.

⚠️ **Note the overlap:** `ag2.network.policies` and `ag2.network.hub.audit` mean AG2 ships its own governance primitives. Read them early — EACP should compose with them, and DECISION_FRAMEWORK.md must honestly address why a cross-framework control plane still adds value over AG2's built-ins.

**Confidence: HIGH** for the middleware/observer/HITL API (read from wheel source). **MEDIUM** for `ag2.network` multi-agent ergonomics — module layout confirmed, but I did not run a working 3-agent conversation, and this API is ~2 months old.

---

## Running Without a Paid LLM API Key

This is a hard project constraint, and the good news is **all three frameworks ship a first-class fake model**. No mocking library, no VCR cassettes, no Ollama required for the default path.

### Tier 1 (default — for CI, tests, and `--fake` demos): scripted fake models, zero network

| Framework | Mechanism | Confidence |
|-----------|-----------|------------|
| **LangGraph** | `langchain_core.language_models.fake_chat_models` — verified present in `langchain-core` 1.6.5: `FakeListChatModel`, `FakeMessagesListChatModel`, `GenericFakeChatModel`, `FakeChatModel`, `ParrotFakeChatModel`. Use **`FakeMessagesListChatModel`** — it returns full `AIMessage` objects, so you can script `tool_calls` and `usage_metadata` (which is how you exercise cost-budget code with deterministic token counts). | HIGH |
| **ag2** | **`ag2.testing.TestConfig` / `TestClient`** — a purpose-built scripted `LLMClient`. Each "turn" is a `str`, a `ToolCallEvent` (or iterable, for parallel calls), a full `ModelResponse`, or a `BaseException` to simulate provider failure. Also `TrackingConfig`, which wraps a real config with a `MagicMock` to assert on calls. This is the single best testing affordance of the three. | HIGH |
| **CrewAI** | Subclass **`crewai.llms.base_llm.BaseLLM`**. Verified: exactly one `@abstractmethod`, `call(messages, tools=None, callbacks=None, ...)`. ~15 lines for a scripted fake. Pass via `Agent(llm=FakeLLM(...))`. Token-usage plumbing (`_track_token_usage_internal`, `get_token_usage_summary`) comes from the base class for free. | HIGH |

**Design implication:** make the fake-LLM factory part of EACP's public surface, not test-only. A `eacp.testing` module exposing one scripted-script-per-backend is what makes `make demo` work with no keys and doubles as the benchmark's control for latency (real token latency would swamp the control-plane overhead you're actually trying to measure).

### Tier 2 (optional realism): Ollama

Both non-LangGraph frameworks support it natively:

- **CrewAI:** verified in `crewai/llm.py` — `"ollama"` and `"ollama_chat"` are recognized providers; `LLM(model="ollama/llama3.1", base_url="http://localhost:11434")`. Comment at line 565 confirms "Ollama accepts any local model name". Routed through `crewai/llms/providers/openai_compatible/completion.py`. **No `litellm` needed** — see below.
- **ag2:** `ag2[ollama]` extra → `ollama>=0.4.7`.
- **LangGraph:** `langchain-ollama` `1.1.0` → `ChatOllama`.

Keep Ollama a documented opt-in extra (`eacp[local]`), gated behind an env var. Never let CI depend on it.

---

## Key Library Decisions

### Policy schema validation → **pydantic**, not jsonschema

`jsonschema==4.26.0` is already in the graph (via `chromadb`/`mcp`), so this isn't about dependency count. Choose pydantic because:

1. **It's unavoidable and shared.** All three frameworks require pydantic v2 (`crewai`, `ag2`, `langchain-core`). It's the only library all three agree on.
2. **Typed Python objects, not dicts.** The spec demands type hints throughout. `jsonschema` validates and hands back a `dict`; pydantic hands back `Policy` with `mypy` checking every `policy.max_cost_usd` access across the engine and all three adapters. That's the difference between a typo being a runtime `KeyError` in an adapter and a CI failure.
3. **You still get JSON Schema.** `Policy.model_json_schema()` emits a publishable schema for docs and editor completion on the YAML files — so you get the jsonschema deliverable without the jsonschema code path.
4. Load YAML with `yaml.safe_load` → `Policy.model_validate(...)`. Two lines.

Use `model_config = ConfigDict(extra="forbid")` on policy models. A typo'd policy key that silently no-ops is the worst possible failure mode for a governance tool — fail loudly at load.

**Confidence: HIGH.**

### Run-history store → **stdlib `sqlite3`**, not SQLAlchemy

SQLAlchemy is **not** in the resolved dependency graph — adding it is a genuinely new dependency (plus 2.1.0 requires Python `>=3.11`). For v1 that's unjustified:

- The store is append-mostly: write a run, write N steps, read runs back, filter by workflow/time. That's ~5 hand-written SQL statements.
- The spec's requirement is *pluggable*, which a `RunStore` Protocol with a `SQLiteRunStore` implementation satisfies completely. An ORM does not make it more pluggable — the Protocol does.
- `sqlite3` ships with Python, so the store works in any environment with zero install.

Define the seam as a `typing.Protocol` (mirroring CrewAI's own `HumanInputProvider` pattern) and ship exactly one implementation. Store trace payloads as a JSON `TEXT` column rather than modelling per-step columns — the schema will churn, JSON won't.

Note `aiosqlite` is already transitive (via both `crewai` and `langgraph-checkpoint-sqlite`), so an async store is available later at no dependency cost. Don't reach for it in v1.

**ponytail: stdlib sqlite3 + one Protocol. Add SQLAlchemy only when a second real backend (Postgres) lands — which the spec puts out of scope.**

**Confidence: HIGH.**

### Tracing/metrics → **OpenTelemetry**, not a custom JSON logger

This one looks like it should go the lazy way and doesn't. The deciding fact: **`opentelemetry-sdk`, `opentelemetry-api`, and `opentelemetry-exporter-otlp-proto-http` are already hard core dependencies of `crewai-core`** (`>=1.42,<2`), and `ag2` ships a `TelemetryMiddleware` built on `opentelemetry-sdk`. It resolves to `1.44.0`.

So OTel is already installed and already emitting from one of your three backends. A custom JSON logger wouldn't replace it — it would sit *beside* it, and EACP's whole pitch is "one governance layer instead of three." Shipping a bespoke trace format while CrewAI and AG2 both speak OTel actively undercuts the thesis.

Use OTel as the **emission** format (spans per node/agent, span attributes for policy decisions, and metrics for latency/tokens/tool-success-rate), with a plain `ConsoleSpanExporter`-style default plus an in-memory exporter that feeds the SQLite run store. That gets you the spec's "per-run trace" and "inspect the resulting trace" CLI without standing up a collector, while remaining pointable at Jaeger/Grafana by config — a real adoption argument for a platform team.

Skip: OTel auto-instrumentation packages and any vendor backend. Manual spans only.

**Confidence: HIGH** on the dependency facts; **MEDIUM** that OTel spans are the right *storage* model — hence the recommendation to store your own run/step rows in SQLite and treat OTel as the wire format.

### CLI → **typer**

`typer==0.27.2` and `click==8.5.0` are already in the resolved graph (typer via `chromadb`/`instructor`, click via `crewai`). Zero added cost, so the argparse "it's stdlib" argument buys nothing here. Typer derives the CLI from the type hints you're already required to write, and gives you `rich`-formatted help (`rich==14.3.4` also already present). Use one app with a subcommand per example plus `runs list` / `runs show`, rather than three separate entrypoint scripts.

**Confidence: HIGH.**

### Benchmark output → **stdlib `csv` + `json`, hand-rolled Markdown**

Do not add `tabulate` or `pandas`. `pandas` is not in the graph and is a heavyweight addition for formatting a table with 3 rows and ~6 columns.

- JSON: `json.dump`.
- CSV: `csv.DictWriter`.
- Markdown: one ~10-line function. Compute column widths, join with `|`. That's smaller than the import line's worth of justification.

**ponytail: hand-rolled markdown table. Add `tabulate` when a table needs alignment/wrapping logic, which a 3-row benchmark never will.**

**Confidence: HIGH.**

---

## Testing Strategy With Three Heavy Frameworks

Measured dependency weight (via `uv pip compile`, Python 3.12, linux-x86_64):

| Install set | Resolved packages |
|-------------|-------------------|
| `ag2` alone | **14** |
| `langgraph` + `langchain` + checkpoint-sqlite | **42** |
| `crewai` alone | **134** |
| All three together | **156** |

**CrewAI is 86% of the dependency surface** — it pulls `chromadb`, `lancedb`, `onnxruntime`, `pyarrow`, `kubernetes`, `grpcio`, `uvicorn`, `textual`, `pdfplumber`, `openpyxl`. This single fact should drive both packaging and test layout.

### Packaging: adapters go in extras

```toml
[project]
dependencies = ["pydantic>=2.11,<2.13", "pyyaml>=6", "typer>=0.27",
                "opentelemetry-sdk>=1.42,<2", "opentelemetry-api>=1.42,<2"]

[project.optional-dependencies]
langgraph = ["langgraph>=1.2,<1.3", "langchain-core>=1.6,<2", "langgraph-checkpoint-sqlite>=3.1"]
crewai    = ["crewai>=1.15,<2"]
autogen   = ["ag2>=1.1,<2"]
local     = ["langchain-ollama>=1.1", "ag2[ollama]>=1.1"]
all       = ["eacp[langgraph,crewai,autogen]"]
```

The control-plane core must import with **zero** framework installed. This is not just hygiene — it's the proof that the abstraction is real rather than LangGraph-shaped, and it's what lets a team adopt EACP for one framework without installing the other two. Adapters import their framework lazily inside `__init__` or behind `TYPE_CHECKING`, and the registry raises a clear "install `eacp[crewai]`" error on a missing backend.

### Test layout

```
tests/
  core/          # engine, policy, store, benchmark. NO framework imports. Fast.
  adapters/
    test_langgraph.py   # @pytest.mark.langgraph
    test_crewai.py      # @pytest.mark.crewai
    test_autogen.py     # @pytest.mark.autogen
  contract/      # one parametrized suite every adapter must satisfy
```

Five rules that matter:

1. **The bulk of tests live in `tests/core/` and import no framework.** Policy evaluation, budget arithmetic, the run store, and Markdown/CSV rendering are all pure logic. They should run in ~1s with 5 dependencies installed.
2. **A shared contract suite is the highest-value test in the project.** Parametrize one suite over all installed adapters asserting identical *observable* behaviour: a forbidden tool is blocked, a budget overage halts the run, an approval node pauses and resumes, a trace has N steps. If the same assertions pass on all three backends, the vendor-agnostic claim is demonstrated rather than asserted — and that suite is the single most persuasive artifact for a reviewer.
3. **Markers + `--strict-markers`,** with `collect_ignore` or `pytest.importorskip` so a missing framework skips rather than errors. Run a `core`-only CI job (fast, gates every push) separately from the `all` job.
4. **Never touch the network.** Use each framework's native fake (above), not `vcrpy`/`respx`. Ollama-backed tests get their own opt-in marker gated on an env var; they are not part of CI.
5. **Reset CrewAI's global hooks between tests.** CrewAI hook registration is process-global, so hooks leak across tests and will produce baffling cross-test failures. `clear_all_global_hooks()` in an `autouse` fixture. ag2 has no such issue — its middleware is per-`Agent` instance.

Set `asyncio_mode = "auto"` in pytest config: `ag2`'s entire middleware surface is `async def`, and CrewAI has async executor paths.

Add `pytest-cov` (`7.1.0`) if you want a coverage badge. Skip `hypothesis` for v1 — property tests are tempting for the policy engine but YAGNI until the policy grammar stabilizes.

**Confidence: HIGH** on structure and the CrewAI global-hook hazard (`clear_all_global_hooks` exists precisely because of it, per its own docstring: *"Useful for testing, resetting state"*).

---

## Installation

```bash
# uv is the toolchain (0.12.19)
uv init --python 3.12
uv add "pydantic>=2.11,<2.13" "pyyaml>=6" "typer>=0.27" \
       "opentelemetry-sdk>=1.42,<2" "opentelemetry-api>=1.42,<2"

# Adapters as extras
uv add --optional langgraph "langgraph>=1.2,<1.3" "langchain-core>=1.6,<2" "langgraph-checkpoint-sqlite>=3.1"
uv add --optional crewai    "crewai>=1.15,<2"
uv add --optional autogen   "ag2>=1.1,<2"
uv add --optional local     "langchain-ollama>=1.1" "ag2[ollama]>=1.1"

# Dev
uv add --dev "pytest>=9.1" "pytest-asyncio>=1.4" "pytest-cov>=7.1" "ruff>=0.16" "mypy>=2.3"

# Verify the full graph resolves before writing any code
uv lock --extra langgraph --extra crewai --extra autogen
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `ag2>=1.1` | `autogen==0.14.1` (AG2 Classic) | If the classic `ConversableAgent` + `GroupChat` + `register_hook` conversation model is required verbatim, or if ag2 1.x's `network` API proves too immature during the spike. It genuinely works, is on the same Python range, has an `[ollama]` extra, and has far more community material. Cost: you build the adapter on an explicitly maintenance-mode API. **Time-box a spike on ag2 1.x first; this is the documented fallback.** |
| `ag2>=1.1` | `agent-framework==1.19.0` (Microsoft) | If the goal shifts to "governs the frameworks Microsoft-shop platform teams actually run in 2026." It's actively developed and arguably more enterprise-relevant than either AutoGen line. But it is not AutoGen, so it changes the project's stated scope — treat as a post-v1 4th adapter that proves the interface extends. |
| pydantic | jsonschema | If policies must be authored/validated by non-Python tools, or you need to publish a schema as the normative spec. You can have both: keep pydantic as the runtime type and emit `model_json_schema()` as an artifact. |
| stdlib `sqlite3` | SQLAlchemy | When a second backend (Postgres) becomes real — explicitly out of scope for v1. |
| OpenTelemetry | Custom JSON logger | Only if you drop the CrewAI adapter entirely (which removes OTel from the graph). With CrewAI present, a custom logger is strictly additive complexity. |
| typer | argparse | If you later want the core CLI installable with zero non-stdlib deps. Not a real constraint here — typer arrives transitively regardless. |
| Native fakes | `vcrpy` / `pytest-recording` | If you eventually want regression tests against real provider responses. Cassettes are a maintenance burden and leak keys/PII; the native fakes cover the control-plane logic, which is all that needs testing. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **`pyautogen`** | Dead. `0.10.0`, last released 2025-07-15, and it's only a proxy shim declaring a dependency on `autogen-agentchat` — which is itself in maintenance mode. Two layers of stale. | `ag2>=1.1` |
| **`autogen-agentchat` / `autogen-core` / `autogen-ext`** | Microsoft's line, `0.7.5`, last released **2025-09-30** — roughly a year stale. Microsoft folded AutoGen into Microsoft Agent Framework in Oct 2025; these get security patches only. | `ag2>=1.1` (or `agent-framework` if targeting Microsoft's successor) |
| **Assuming `ag2` imports as `autogen`** | It did through 0.14.x. It does **not** in 1.x — verified: the wheel's only top-level package is `ag2/`. `from autogen import ConversableAgent` against `ag2==1.1.0` raises `ModuleNotFoundError`, and `ConversableAgent` does not exist anywhere in the distribution. This is the #1 way stale training data breaks this build. | `from ag2 import Agent, Middleware, Task` |
| **`pip install ag2-classic`** | No such PyPI package. It's a GitHub repo name (`ag2ai/ag2-classic`). | `pip install autogen` for the classic API |
| **`pydantic>=2.13`** | `crewai-core==1.15.22` requires `pydantic<2.13,>=2.11.9`. Unpinned installs resolve to 2.13.5 and then conflict the moment CrewAI enters the graph. | `pydantic>=2.11,<2.13` (resolves to `2.12.5`) |
| **CrewAI's `step_callback` / `task_callback` for tracing** | Coarse, positional-callback-based, and superseded. CrewAI 1.15 ships ~20 typed event modules on `crewai.events` plus a dedicated `crewai.hooks` package with abort support. | `crewai.events.BaseEventListener` for tracing; `crewai.hooks` for enforcement |
| **Monkey-patching any framework to inject policy** | Unnecessary in 2026 and fatal to the project's credibility as something a maintainer would review favourably. All three expose real interception seams: LangGraph node wrapping/`error_handler`, `crewai.hooks` + `HookAborted`, `ag2` `BaseMiddleware.on_tool_execution`. | The documented hook APIs above |
| **`langgraph` without a checkpointer** | `interrupt()`/`Command(resume=...)` and all durable-execution features require one. `compile(checkpointer=False)` explicitly disables interrupts. | `SqliteSaver` from `langgraph-checkpoint-sqlite` |
| **`pandas` / `tabulate` for benchmark output** | Formatting a ~3×6 table. `pandas` isn't in the graph and is a very large addition for `str.join`. | stdlib `csv`, `json`, ~10 lines of Markdown |
| **SQLAlchemy in v1** | Not in the resolved graph — a genuinely new dependency for ~5 SQL statements against a store the spec scopes to SQLite. | stdlib `sqlite3` behind a `Protocol` |
| **`vcrpy` / `respx` / `unittest.mock` for LLM calls** | All three frameworks ship purpose-built scripted fakes that are deterministic, support tool calls, and require no network. Mocking at the HTTP layer is strictly more fragile. | `FakeMessagesListChatModel`, `ag2.testing.TestConfig`, `BaseLLM` subclass |
| **Making `crewai` a core dependency** | 134 of the 156 total packages, including `onnxruntime`, `lancedb`, `pyarrow`, `kubernetes`. Forces every user to install all of it to govern a LangGraph workflow. | `eacp[crewai]` extra + lazy import |
| **Intel Mac (x86_64 macOS) as a dev/CI target** | Hard blocker, verified: `crewai>=1.15` requires `lancedb>=0.29.2,<0.30.1`, and that range publishes **no `macosx_*_x86_64` wheels** (only `macosx_11_0_arm64`, manylinux, win_amd64). `uv pip compile --python-platform x86_64-apple-darwin` fails to resolve. | Apple Silicon, Linux, or Windows. Document it. |

---

## Version Compatibility

Verified by real resolution: `uv pip compile --python-version 3.12` over all three frameworks simultaneously.

| Package | Resolves to | Notes |
|---------|-------------|-------|
| `langgraph` | `1.2.12` | — |
| `langchain` | `1.4.2` | Pins `langgraph>=1.2.11,<1.3.0`. Compatible with `langgraph` 1.2.12 by construction — but **upgrading `langgraph` to 1.3 will require a `langchain` major bump.** Pin both. |
| `langchain-core` | `1.6.5` | — |
| `crewai` / `crewai-core` / `crewai-cli` | `1.15.22` | Split into three distributions in 1.x; versions move in lockstep. |
| `ag2` | `1.1.0` | Imports as **`ag2`**. |
| **`pydantic`** | **`2.12.5`** | ⚠️ **The critical pin.** `crewai-core` caps `<2.13`; `ag2` (`>=2.6.1,<3`) and `langchain-core` (`>=2.7.4,<3`) are both permissive. CrewAI is the binding constraint. Without CrewAI you'd get 2.13.5. |
| `openai` | `2.54.0` | Pulled by `crewai` core (**not** litellm — CrewAI 1.x uses native provider clients; `litellm` is now merely an extra). Installed even when you never call OpenAI. |
| `opentelemetry-*` | `1.44.0` | Core dep of `crewai-core` (`>=1.42,<2`). `ag2[tracing]` wants `>=1.20`. No conflict. |
| `typer` / `click` | `0.27.2` / `8.5.0` | Both already transitive. `crewai` caps `click<9`. |
| `lancedb` | `0.30.0` | ⚠️ Platform-constrained — no macOS x86_64 wheel. See above. |
| **Python** | `3.11`–`3.13` | `crewai` caps `<3.14`; everything else allows `>=3.10`. Recommend **3.12**. |
| Total | **156 packages** | On linux-x86_64 and aarch64-apple-darwin. |

**Resolution results by platform** (verified):

| Platform | Result |
|----------|--------|
| `x86_64-unknown-linux-gnu` | ✅ resolves (156 pkgs) |
| `aarch64-apple-darwin` | ✅ resolves (156 pkgs) |
| `x86_64-apple-darwin` | ❌ **fails** — `lancedb` has no matching wheel |

Commit `uv.lock`. With 156 packages across three fast-moving frameworks, reproducible benchmark numbers are otherwise impossible — and the benchmark is a headline deliverable.

---

## Explicit Staleness Audit

Per the quality gate — what was verified vs. assumed:

**Verified from primary sources (HIGH confidence):**
- All version numbers and release dates — PyPI JSON API, fetched 2026-09-24.
- `ag2` 1.1.0 has no `ConversableAgent`/`register_hook`, top-level package is `ag2` — read the published wheel's 444 source files directly.
- `autogen` 0.14.1 has `register_hook` in `autogen/agentchat/conversable_agent.py`, `GroupChat` in `groupchat.py` — read the wheel.
- ag2 middleware API (`on_turn`/`on_llm_call`/`on_tool_execution`), builtin list, `ag2.testing.TestConfig`, `Agent(hitl_hook=, middleware=, observers=)` — read `ag2/middleware/base.py`, `builtin/__init__.py`, `testing.py`, `agent.py`.
- CrewAI `crewai.hooks` public API, `HookAborted`, `InterceptionPoint` values, `ToolCallHookContext` fields + in-place-mutation requirement, `BaseLLM` single abstractmethod, `LLMCallBlockedError`, `HumanInputProvider` Protocol, SQLite checkpoint provider, Ollama provider support — read the `crewai` 1.15.22 wheel.
- `langchain-core` 1.6.5 fake chat model class names — read the wheel.
- LangGraph `interrupt`/`Command(resume=)`/`SqliteSaver`/`get_state_history`/`error_handler` — Context7 `/websites/langchain_oss_python_langgraph` (current docs).
- pydantic `<2.13` conflict, 156-package count, per-framework dependency weights, macOS x86_64 `lancedb` failure — real `uv pip compile` runs across three target platforms.
- AG2 v1.0 removed the classic framework and relocated it to `ag2ai/ag2-classic` — GitHub releases page.

**Assumed / not verified (flagged):**
- **MEDIUM** — `ag2.network` multi-agent ergonomics. Module layout confirmed from the wheel; I did **not** execute a working 3-agent conversation. The incident-response example depends on this. **Spike this before committing to the AutoGen adapter design.**
- **MEDIUM** — AG2 v1.0.0/v1.1.0 release dates. The release-notes fetch reported "July 27, 2024" and "September 24, 2024", which contradicts PyPI upload timestamps (2026-07-27 and 2026-09-24). PyPI is authoritative; the summarizer almost certainly mangled the year. Dates above use PyPI.
- **MEDIUM** — CrewAI's checkpoint/restore API as a pause-resume mechanism. Modules and events confirmed present; semantics not tested.
- **MEDIUM** — That OTel spans are the right *storage* model for run history. Hence the split recommendation: OTel as wire format, own SQLite rows as storage.
- **LOW** — Long-term stability of `ag2` 1.x. Four releases in the last month; 0.13.1 → 1.1.0 in four months. Pin exactly and expect breakage on minor bumps.
- **Not investigated** — whether `crewai` can be installed without `chromadb`/`lancedb`. They are core (not extra) deps of `crewai` 1.15.22, so likely not, but a `crewai-core`-only adapter path might exist and would cut the dependency graph dramatically. Worth 30 minutes.

---

## Sources

- **PyPI JSON API** (`pypi.org/pypi/{pkg}/json`) — all versions, release dates, `requires_python`, `requires_dist`, extras. Fetched 2026-09-24. HIGH.
- **Published wheels, inspected directly** — `ag2-1.1.0`, `autogen-0.14.1`, `crewai-1.15.22`, `langchain_core-1.6.5`. Source-level verification of every hook/API claim. HIGH.
- **`uv pip compile` 0.12.19** — cross-framework resolution, pydantic conflict, platform support matrix. HIGH.
- **Context7 `/websites/langchain_oss_python_langgraph`** — topics: interrupt/`Command` resume, checkpointers, `SqliteSaver`, `get_state_history`, fault-tolerance `error_handler`, subgraph persistence. HIGH.
- https://docs.ag2.ai/latest/docs/contributor-guide/how-ag2-works/hooks/ — AG2 hook model. MEDIUM (documents the classic 4-hook `register_hook` model; superseded by middleware in 1.x — an example of official docs lagging the code).
- https://github.com/ag2ai/ag2/releases — v1.0.0 classic removal + `ag2ai/ag2-classic` relocation. MEDIUM (dates mangled by summarizer; corrected against PyPI).
- https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/ — official AutoGen → Agent Framework migration path. MEDIUM.
- https://devblogs.microsoft.com/agent-framework/migrate-your-semantic-kernel-and-autogen-projects-to-microsoft-agent-framework-release-candidate/ — AutoGen/Semantic Kernel merger. MEDIUM.
- https://github.com/ag2ai/ag2 — AG2 project status, maintainership. MEDIUM.
- https://dev.to/felipejac/autogen-is-in-maintenance-mode-migrating-to-agent-framework-39co — AutoGen maintenance-mode corroboration. LOW (corroborates the Microsoft Learn + PyPI evidence; not relied on alone).

---
*Stack research for: vendor-agnostic multi-agent control plane (Python)*
*Researched: 2026-09-24*
