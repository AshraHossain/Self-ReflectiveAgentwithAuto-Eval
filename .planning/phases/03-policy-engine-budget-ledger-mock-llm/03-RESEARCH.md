# Phase 3: Policy Engine, Budget Ledger & Mock LLM - Research

**Researched:** 2026-10-05 (completes the 2026-10-04 checkpoint; all of its findings are kept and re-verified below)
**Domain:** Pure policy decision function, SQLite-backed budget ledger with cross-process atomic admission, framework-free scripted mock LLM
**Confidence:** HIGH for the mechanics (each one was executed against the project venv in this session). The five schema/semantics choices are recommendations that need the user to confirm them (see Assumptions Log).

## Summary

Phase 3 builds three small core modules and makes one schema change. Nothing in it needs an agent framework or a new dependency. Python 3.12.13, SQLite 3.53.2, pydantic 2.12.5 and pytest 9.1.1 already cover all of it. Planning hinges on three verified facts:

1. **The existing store's transaction pattern over-admits when copied into the ledger.** I ran a race probe: 4 processes each did 10 check-then-reserve attempts against a cap of 10. With `store.py`'s style (legacy implicit transactions), **20–39 calls were admitted**, and updates were also lost (one run admitted 30 but recorded only 0.6 of 1.0 spend). With `isolation_level=None` + explicit `BEGIN IMMEDIATE`, exactly **10 of 10 were admitted, every run**. The ledger therefore must not copy `with closing(self._connect()) as c, c:` from `store.py`.
2. **`tiktoken` is not in the dependency graph at all.** `grep tiktoken uv.lock` returns nothing. `.planning/research/PITFALLS.md:180` says it is "already a transitive dep", which is wrong for this lock. Pre-call estimates use a deterministic char-based heuristic tagged `estimated`. Reconciliation then replaces the estimate with provider usage.
3. **Default `Decimal.quantize` rounds tiny costs down to zero.** 1 token at $0.10/Mtok is `1E-7`, which quantizes to `0.000000` under the default ROUND_HALF_EVEN. That is exactly the "usage silently reads zero" failure BUDGET-05 forbids. Cost computation must quantize with `ROUND_CEILING`.

The policy schema needs two new **required** fields: `max_steps` (BUDGET-04) and `model_prices` (needed to turn token usage into the money that `max_cost_per_day` is denominated in). Both change `policy_hash`. Both mean updating five test sites that are named below.

**Primary recommendation:** Build `engine.py` as a pure function `decide(policy, request, state) -> Decision` with no clock, no I/O and no framework imports. Build `ledger.py` as `SQLiteBudgetLedger`: it reads state, calls `decide()` and writes the reservation inside one `BEGIN IMMEDIATE` transaction, and it raises `PolicyDenied(decision)` on deny. Build `mock_llm.py` as a scripted `MockLLM` whose turns carry non-zero `Usage` tagged `provider`, with a `loop=True` runaway mode. `[]` in `allowed_tools` means deny-all. An unpriced model is denied (fail-closed).

<user_constraints>
## User Constraints (from CONTEXT.md)

**No CONTEXT.md exists.** The user chose to plan without `/gsd-discuss-phase`. That leaves no locked decisions, discretion areas or deferred ideas for this phase specifically. The binding constraints come from:

### Locked by prior phases (do not relitigate)
- **D-06** `RunStore` is synchronous; ag2 bridges via `asyncio.to_thread` inside its adapter. [VERIFIED: .planning/STATE.md, Phase 2 decisions]. The ledger is synchronous for the same reason.
- **D-08 / D-12** "Every field is required: absence never means unlimited" [VERIFIED: src/eacp/policy.py:71]. This drives the recommendations that new fields are required, `[]` is deny-all and an unpriced model is denied.
- **D-11** `policy_id` and `version` are identity, not content, and are excluded from the hash: `_IDENTITY_FIELDS: frozenset[str] = frozenset({"policy_id", "version"})` [VERIFIED: src/eacp/policy.py:113].
- **T-02-08** A new field must be deliberately classified as content or identity, and `test_hashed_key_set_is_pinned` enforces this [VERIFIED: tests/test_policy.py:214-226].
- **v2-deferred (OUT OF SCOPE):** dry-run/shadow (`enforce|warn|off`) mode, per-tenant policy scoping, control-plane overhead benchmark [VERIFIED: .planning/REQUIREMENTS.md v2 section]. `.planning/research/SUMMARY.md:104` lists "dry-run/shadow mode" under Phase 3. **Ignore that line.** The user deferred it afterwards, and REQUIREMENTS.md is the later source.

### Open decisions: recommendations for the planner to adopt (the user should confirm)

| # | Decision | Recommendation | Why |
|---|----------|----------------|-----|
| OD-1 | `max_steps` schema change | Add **required** `max_steps: Annotated[StrictInt, Field(ge=1)]` to `Policy`. It is content (hashed), not identity. | D-12: absence is never unlimited. BUDGET-04 needs a per-policy ceiling. |
| OD-2 | Token pricing source | Add **required** `model_prices: dict[str, ModelPrice]` to `Policy`. `ModelPrice` = `{input_per_mtok: Decimal, output_per_mtok: Decimal}`, quantized like cost. **Unknown model → deny** with rule `model_prices`. No pricing table ships in core. | The price that governed a run is then pinned by `policy_hash`, which makes the run reproducible. A shipped table goes stale and nobody owns it. Fail-closed matches D-12. The mock is priced as `mock` in fixtures, so cost is non-zero in tests. |
| OD-3 | `allowed_tools: []` semantics | **Deny-all.** An empty allowlist allows no tool. `forbidden_tools` is checked first and wins. No `"*"` wildcard in v1. | `ARCHITECTURE.md:172`'s `if ctx.policy.allowed_tools and ...` makes `[]` mean allow-all, which contradicts D-08/D-12. Add a wildcard when someone needs one. |
| OD-4 | Cross-process admission | One SQLite transaction: `isolation_level=None`, `BEGIN IMMEDIATE`, read state, pure `decide()`, write reservation, `COMMIT`. On exception, `ROLLBACK` only `if c.in_transaction`. | The probe in this session showed legacy mode over-admitting 2–4x. BEGIN IMMEDIATE was exact in 6/6 runs. |
| OD-5 | Pre-call estimation without tiktoken | `estimate_tokens(text) = ceil(len(text) / 4)`, tagged `estimated`. Output estimate = `min(max_output_tokens, remaining_run_tokens)`, or `remaining_run_tokens` when the caller gives no ceiling. | Zero dependencies and deterministic. Reconciliation corrects it to provider actuals, and the remaining error is the documented one-call overshoot bound. Adapters may pass a better input count (e.g. LangChain `get_num_tokens`) through the same `LlmCall.input_tokens` field. |
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| POLICY-03 | `decide()` is pure (no I/O, no clock, no framework imports) and returns a structured `Decision` (policy id, version, rule, limit, observed), never a bare boolean | Pattern 1 (`engine.py`), AST import-allowlist purity test, invariant "numeric deny iff observed > limit" |
| BUDGET-01 | Pre-call admission: estimate before the call, hard block if it would exceed the limit | Pattern 2 (`ledger.admit` under BEGIN IMMEDIATE raises `PolicyDenied`). OD-4, OD-5. Early-stop test asserts LLM **call count** |
| BUDGET-02 | Post-call reconciliation updates actual usage against the pre-call estimate | `ledger.reconcile(admission, usage)` applies `actual - estimate` to the reservation's **own** date key, and DELETEs the reservation row (a second reconcile raises `KeyError`) |
| BUDGET-03 | Daily cost counter persisted, keyed by policy + UTC date | `daily_spend(policy_id, utc_date)` PRIMARY KEY, money as TEXT Decimal. Restart test uses a fresh subprocess. A new date means a new row, so no reset logic is needed |
| BUDGET-04 | Independent `max_steps` ceiling | OD-1. A step is every admitted governed call (LLM **or** tool), counted in `run_usage.steps` |
| BUDGET-05 | Every usage reading carries `usage_source` (`provider`/`estimated`/`MISSING`); never coerced to zero | `Usage.__post_init__` enforces "MISSING ⇔ tokens are None". MISSING is charged at the estimate and counted in `run_usage.missing_usage`. `ROUND_CEILING` cost |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Python 3.11+ with type hints. The project runs `mypy --strict` over `src` and `tests` [VERIFIED: pyproject.toml `[tool.mypy] strict = true`, `files = ["src", "tests"]`].
- Runnable without paid keys. A local/mock model path is mandatory, and this phase's `MockLLM` is that path.
- Persistence is simple and pluggable: SQLite for v1 using stdlib `sqlite3`, no SQLAlchemy. Money stays `Decimal`, never float (Phase 2 convention).
- Core must never import langgraph/crewai/ag2 (PACKAGE-01). All three new modules are core.
- Do not monkey-patch frameworks. (This phase does not touch frameworks.)
- `yaml.safe_load` only. In practice the project uses its stricter `_StrictLoader`, and `model_prices` arrives through the same `load_policy_file` path, so no new YAML entry point is needed.
- GSD workflow: edits only via `/gsd-execute-phase`.
- `filterwarnings = ["error::DeprecationWarning"]`: never hand a `datetime` to sqlite3 [VERIFIED: pyproject.toml].
- `ponytail:` comments mark deliberate ceilings (existing convention in store.py:187, 191).

## Architectural Responsibility Map

The tiers here are a library's internal layers, not web tiers.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Rule evaluation (`decide`) | Pure core (`engine.py`) | — | POLICY-03: no I/O/clock. It is unit-testable against tables of cases |
| Token/cost estimation, cost arithmetic | Pure core (`engine.py`) | — | Deterministic functions of the request and price |
| Budget state, admission locking, reconciliation | Storage (`ledger.py`, SQLite) | Pure core (calls `decide`) | Atomicity must live where the lock is. The ledger owns the clock (UTC date) |
| Policy schema (`max_steps`, `model_prices`) | Trust boundary (`policy.py`) | — | The only place YAML becomes typed data |
| Scripted model | Core utility (`mock_llm.py`) | Adapters (Phases 5–7 wrap it in framework fakes) | Framework-free core script; per-framework shims belong to their adapters |
| Raising on deny | Ledger (`PolicyDenied`) | Adapters (PEPs) catch/translate | Returning a bool the caller must remember to check is the "silent bypass" anti-pattern (ARCHITECTURE.md Pattern 1, option B) |

## Standard Stack

### Core (all already installed; nothing to add)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `sqlite3` (stdlib) | SQLite 3.53.2 [VERIFIED: venv probe] | Ledger persistence + cross-process lock | Already the store backend. `BEGIN IMMEDIATE` gives a reserved write lock up front |
| `decimal` (stdlib) | — | Money arithmetic | Existing `_COST_EXP = Decimal("0.000001")` [VERIFIED: src/eacp/policy.py:28] |
| `math.ceil` (stdlib) | — | Token estimate | Replaces tiktoken (absent) |
| `itertools.cycle` (stdlib) | — | Mock runaway mode | One line |
| pydantic | 2.12.5 [VERIFIED: venv probe] | `ModelPrice` nested model | Already the schema library. Nested-model dump is hash-stable (probe below) |
| pytest | 9.1.1 [VERIFIED: tests run in session: 77 passed in 1.12s] | Tests | Existing |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `BEGIN IMMEDIATE` + Python Decimal | Single atomic `UPDATE ... SET spent = spent + ? WHERE spent + ? <= ?` on INTEGER micro-units | One statement and no explicit transaction. But `decide()` could then no longer run inside the lock, so the Decision's `observed` would come from a second, racy read, and run tokens/steps/reservation would need the same treatment. Rejected |
| ceil(chars/4) | `tiktoken` | New dependency that is not in the lock, and model-specific anyway. Rejected for core. Adapters can supply better counts |
| Prices in `Policy` | Shipped `model→price` table in core | Goes stale and isn't hash-pinned. Rejected (OD-2) |
| One `PolicyDenied` error | `BudgetExceededError` / `ToolDeniedError` / `StepLimitError` (03-PATTERNS.md suggestion) | The `Decision.rule` already says which one fired. Three classes duplicate it. Use one class carrying the `Decision` |
| Concrete `SQLiteBudgetLedger` | `BudgetLedger` Protocol + impl (03-PATTERNS.md suggestion) | One implementation, and the spec only requires run-history pluggability. Add a Protocol when a second ledger backend appears |

**Installation:** none. No new packages.

## Package Legitimacy Audit

This phase installs no external packages. Everything is stdlib or already locked (`pydantic` 2.12.5). `tiktoken` was considered and **not** recommended (OD-5).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | — |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
 adapter PEP (Phase 5-7) / test driver (Phase 3)
        |
        | LlmCall(model, input_tokens est., max_output_tokens) | ToolCall(tool_name)
        v
 SQLiteBudgetLedger.admit(run_id, policy, request)
        |  BEGIN IMMEDIATE  (cross-process write lock; readers unaffected under WAL)
        |  read daily_spend[policy_id, today_utc] + run_usage[run_id]
        |        -> BudgetState(steps_taken, run_tokens, spent_today)
        |  engine.decide(policy, request, state)   <-- pure, no I/O, no clock
        |        |
        |   deny +--> ROLLBACK -> raise PolicyDenied(decision)  (call never executes)
        |        |
        |  allow +--> steps+1; [LLM] tokens+=est, spent+=est_cost, INSERT reservation
        |  COMMIT -> return Admission(decision, reservation_id, utc_date, est_tokens, est_cost)
        v
 MockLLM.complete(...)  /  real model  /  tool callable
        |
        | Usage(input_tokens, output_tokens, usage_source)
        v
 SQLiteBudgetLedger.reconcile(admission, usage)      [LLM calls only]
        |  BEGIN IMMEDIATE
        |  DELETE reservation (rowcount 0 -> KeyError: double/unknown reconcile)
        |  actual = usage tokens/cost, or the ESTIMATE if usage_source == "MISSING"
        |  daily_spend[policy_id, admission.utc_date] += actual_cost - est_cost
        |  run_usage.tokens += actual_tokens - est_tokens; missing_usage += (MISSING)
        |  COMMIT
```

### Recommended Project Structure
```
src/eacp/
├── engine.py      # NEW. Pure: Decision, LlmCall, ToolCall, BudgetState, Usage, decide(),
│                  #      estimate_tokens(), cost_of(). Imports: stdlib + eacp.policy only
├── ledger.py      # NEW. SQLiteBudgetLedger: admit(), reconcile(), spent_today(), run_usage()
├── mock_llm.py    # NEW. MockLLM, MockTurn, MockToolCall
├── policy.py      # MOD. + max_steps, + model_prices/ModelPrice; _COST_EXP -> COST_EXP (public)
└── errors.py      # MOD. + PolicyDenied
tests/
├── conftest.py        # MOD. _VALID_POLICY += max_steps, model_prices
├── test_policy.py     # MOD. ALL_FIELDS, _HASH_A/_HASH_B, hash-moves params, pinned key set
├── test_engine.py     # NEW
├── test_ledger.py     # NEW (incl. subprocess race + restart tests)
└── test_mock_llm.py   # NEW (incl. end-to-end early-stop with call-count assertion)
```

### Pattern 1: Pure `decide()` with a structured Decision (POLICY-03)

**What:** A total function over `(Policy, request, BudgetState)`. Rules are evaluated in a fixed order. A deny reports the first rule that fails. An allow reports the *last* rule checked: `allowed_tools` for tool calls, `max_cost_per_day` for LLM calls. **Invariant for numeric rules: `outcome == "deny"` ⇔ `observed > limit`, where `observed` is the *projected* value (current + this call).** That invariant is one parametrized test.

The rule names are exactly the policy field names that decided the outcome. Phase 4's audit log then needs no mapping table.

```python
# src/eacp/engine.py -- skeleton. Field names on Policy quoted from src/eacp/policy.py:79-88
# plus the two OD-1/OD-2 additions. COST_EXP is the renamed _COST_EXP (policy.py:28).
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from typing import Literal

from eacp.policy import COST_EXP, ModelPrice, Policy

UsageSource = Literal["provider", "estimated", "MISSING"]
Rule = Literal[
    "max_steps", "forbidden_tools", "allowed_tools",
    "model_prices", "max_tokens_per_run", "max_cost_per_day",
]
Observed = int | Decimal | str
Limit = int | Decimal | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Decision:
    outcome: Literal["allow", "deny"]   # Phase 4 adds "require_approval"; widening a Literal is additive
    policy_id: str
    version: int
    rule: Rule
    limit: Limit
    observed: Observed


@dataclass(frozen=True, slots=True)
class LlmCall:
    model: str
    input_tokens: int                 # caller's estimate (estimate_tokens) or a better count
    max_output_tokens: int | None


@dataclass(frozen=True, slots=True)
class ToolCall:
    tool_name: str


@dataclass(frozen=True, slots=True)
class BudgetState:
    steps_taken: int
    run_tokens: int
    spent_today: Decimal


def estimate_tokens(text: str) -> int:
    # ponytail: chars/4 heuristic (no tiktoken in core). Underestimates code/CJK; the error
    # is bounded to one call by reconciliation. Upgrade: adapters pass a tokenizer count.
    return math.ceil(len(text) / 4)


def cost_of(price: ModelPrice, input_tokens: int, output_tokens: int) -> Decimal:
    raw = (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / 1_000_000
    return raw.quantize(COST_EXP, rounding=ROUND_CEILING)  # never round a real cost to 0


def output_estimate(policy: Policy, req: LlmCall, state: BudgetState) -> int:
    remaining = max(policy.max_tokens_per_run - state.run_tokens - req.input_tokens, 0)
    return remaining if req.max_output_tokens is None else min(req.max_output_tokens, remaining)


def decide(policy: Policy, request: LlmCall | ToolCall, state: BudgetState) -> Decision:
    def mk(ok: bool, rule: Rule, limit: Limit, observed: Observed) -> Decision:
        return Decision("allow" if ok else "deny", policy.policy_id, policy.version,
                        rule, limit, observed)

    steps = state.steps_taken + 1
    if steps > policy.max_steps:
        return mk(False, "max_steps", policy.max_steps, steps)
    if isinstance(request, ToolCall):
        name = request.tool_name
        if name in policy.forbidden_tools:
            return mk(False, "forbidden_tools", tuple(policy.forbidden_tools), name)
        # OD-3: [] allows nothing.
        return mk(name in policy.allowed_tools, "allowed_tools", tuple(policy.allowed_tools), name)
    price = policy.model_prices.get(request.model)
    if price is None:  # OD-2: unpriced model is fail-closed
        return mk(False, "model_prices", tuple(sorted(policy.model_prices)), request.model)
    out = output_estimate(policy, request, state)
    tokens = state.run_tokens + request.input_tokens + out
    if tokens > policy.max_tokens_per_run:
        return mk(False, "max_tokens_per_run", policy.max_tokens_per_run, tokens)
    spend = state.spent_today + cost_of(price, request.input_tokens, out)
    return mk(spend <= policy.max_cost_per_day, "max_cost_per_day", policy.max_cost_per_day, spend)


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int | None
    output_tokens: int | None
    usage_source: UsageSource

    def __post_init__(self) -> None:
        missing = self.usage_source == "MISSING"
        for n in (self.input_tokens, self.output_tokens):
            if (n is None) is not missing:
                raise ValueError("MISSING usage carries no counts; any other source requires both")
            if n is not None and (isinstance(n, bool) or n < 0):
                raise ValueError("token counts must be non-negative ints")
```

Note on `output_estimate`: with no caller ceiling, the output estimate fills the run's remaining tokens. The token check can then only fire when the *input* estimate alone exceeds what remains, and output overshoot is bounded to one call. That is the honest bound PITFALLS.md Pitfall 5 asks to be documented. A caller-supplied `max_output_tokens` tightens the cost reservation.

### Pattern 2: Ledger admission under `BEGIN IMMEDIATE` (BUDGET-01/02/03/04)

**What:** Each `admit`/`reconcile` is one short write transaction on its own connection. The constructor setup is copied from `store.py:171-189`: mkdir, `touch(mode=0o600)` + `chmod(0o600)`, `PRAGMA journal_mode=WAL` first, `executescript`, `PRAGMA user_version=1`. The **transaction style** is the one deliberate deviation.

```python
# src/eacp/ledger.py -- transaction helper and schema
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_spend (
  policy_id TEXT NOT NULL,
  utc_date  TEXT NOT NULL,          -- date.isoformat(), never a date object (deprecated adapter)
  spent     TEXT NOT NULL,          -- str(Decimal), never REAL
  PRIMARY KEY (policy_id, utc_date)
);
CREATE TABLE IF NOT EXISTS run_usage (
  run_id        TEXT PRIMARY KEY,
  steps         INTEGER NOT NULL,
  tokens        INTEGER NOT NULL,
  missing_usage INTEGER NOT NULL DEFAULT 0   -- BUDGET-05: runs with MISSING readings are flagged
);
CREATE TABLE IF NOT EXISTS reservations (
  reservation_id TEXT PRIMARY KEY,
  run_id    TEXT NOT NULL,
  policy_id TEXT NOT NULL,
  utc_date  TEXT NOT NULL,
  tokens    INTEGER NOT NULL,
  cost      TEXT NOT NULL
);
"""

@contextmanager
def _tx(self) -> Iterator[sqlite3.Connection]:
    # isolation_level=None: the driver never opens transactions itself, so BEGIN IMMEDIATE
    # takes the write lock BEFORE the read. Legacy mode opens one only before DML, which let
    # 4 processes admit 20-39 calls against a cap of 10 (03-RESEARCH.md probe). Works on 3.11
    # (Connection.autocommit is 3.12+ only, so it is not used).
    c = sqlite3.connect(self._path, timeout=30.0, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        c.execute("BEGIN IMMEDIATE")
        yield c
        c.execute("COMMIT")
    except BaseException:
        if c.in_transaction:      # BEGIN itself may have failed (busy timeout); don't mask it
            c.execute("ROLLBACK")
        raise
    finally:
        c.close()
```

The UTC date comes from an injected clock, `clock: Callable[[], datetime] = lambda: datetime.now(UTC)`, as a constructor keyword, and is turned into `self._clock().date().isoformat()`. That is how the day-rollover test runs without sleeping. `decide()` never sees the clock.

**Reconcile against the reservation's date, not today's.** A call admitted at 23:59:59 UTC and finished after midnight must correct the day it was charged to. The `Admission` carries `utc_date`.

**MISSING usage:** charge the estimate (tokens and cost unchanged, delta 0), increment `missing_usage`, and return the reading. Never charge zero.

### Pattern 3: Scripted mock LLM (success criterion 4)

```python
# src/eacp/mock_llm.py -- framework-free. Phases 5-7 wrap it in FakeMessagesListChatModel /
# crewai BaseLLM subclass / ag2.testing.TestConfig (CLAUDE.md Tier 1); not this phase.
import itertools
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from eacp.engine import Usage

@dataclass(frozen=True, slots=True)
class MockToolCall:
    name: str
    args: Mapping[str, object] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class MockTurn:
    text: str = ""
    tool_calls: tuple[MockToolCall, ...] = ()
    usage: Usage = Usage(40, 12, "provider")   # non-zero by default (Pitfall 11)

class MockLLM:
    def __init__(self, script: Sequence[MockTurn], *, model: str = "mock", loop: bool = False) -> None:
        if not script:
            raise ValueError("script must contain at least one turn")
        self.model = model
        self.calls = 0
        self._turns: Iterator[MockTurn] = itertools.cycle(script) if loop else iter(script)

    def complete(self, messages: Sequence[Mapping[str, str]]) -> MockTurn:
        try:
            turn = next(self._turns)
        except StopIteration:
            raise RuntimeError(f"mock script exhausted after {self.calls} calls") from None
        self.calls += 1
        return turn
```

It must script: (a) a forbidden tool call, (b) non-zero `provider` usage, (c) a `MISSING` usage turn, and (d) `loop=True` runaway mode. Usage is scripted **explicitly**, never derived from `estimate_tokens`. If the two agreed, every reconciliation delta would be 0 and BUDGET-02 would be tested vacuously.

### Pattern 4: Policy schema additions (OD-1, OD-2)

```python
# src/eacp/policy.py additions. Style matches lines 79-97 verbatim conventions.
class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    input_per_mtok: Annotated[Decimal, Field(ge=Decimal(0))]
    output_per_mtok: Annotated[Decimal, Field(ge=Decimal(0))]

    @field_validator("input_per_mtok", "output_per_mtok")
    @classmethod
    def _quantize(cls, v: Decimal) -> Decimal:  # same body as Policy._quantize (lines 92-97)
        ...

# inside Policy:
    max_steps: Annotated[StrictInt, Field(ge=1)]
    model_prices: dict[_ModelName, ModelPrice]   # _ModelName: a key pattern like _PolicyId,
                                                 # widened with ':' and '/' (e.g. "ollama/llama3.1")
```

Verified in session: with nested `ModelPrice`, `{"input_per_mtok": 1, "output_per_mtok": "3.0"}` and `{"output_per_mtok": 3, "input_per_mtok": "1.00"}` dump to identical sorted JSON (`{"model_prices": {"mock": {"input_per_mtok": "1.000000", "output_per_mtok": "3.000000"}}}`), and `True` is rejected for a price. The hash therefore stays canonical without changes to `policy_hash`.

### Anti-Patterns to Avoid
- **Copying `store.py`'s `with closing(self._connect()) as c, c:` into the ledger.** It is fine for append-only history and wrong for check-then-reserve (probe: 2–4x over-admission plus lost updates).
- **`ledger.admit()` returning a Decision the caller must check.** A forgotten `if` is a silent bypass. Raise `PolicyDenied` on deny and return an `Admission` (which still carries the allow `Decision` for Phase 4's audit) on allow.
- **Calling `datetime.now()` inside `engine.py`.** That breaks POLICY-03, so the clock lives in the ledger.
- **Treating provider `0` like `None`.** `Usage(None, None, "MISSING")` and `Usage(0, 0, "provider")` are different facts.
- **Sharing one SQLite file between `SQLiteRunStore` and the ledger.** Both set `PRAGMA user_version=1` [VERIFIED: src/eacp/store.py:189], so a shared file gives two schemas one migration marker. Default the ledger to its own file (e.g. `ledger.db`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-process mutual exclusion | file locks, `fcntl`, a lock table, retry loops | SQLite `BEGIN IMMEDIATE` + `timeout=30.0` busy handler | Verified exact under 4-process contention, no SQLITE_BUSY surfaced |
| Money arithmetic | floats, integer cents with manual scaling | `Decimal` + `quantize(COST_EXP, rounding=ROUND_CEILING)` | Existing convention. Ceiling prevents rounding a real cost to zero |
| Day rollover / reset job | a cron or "reset at midnight" logic | `(policy_id, utc_date)` key | A new date is a new row. BUDGET-03 already says "keyed by policy + UTC date" [VERIFIED: .planning/REQUIREMENTS.md:31] |
| Runaway mock | custom generator class | `itertools.cycle(script)` | One line |
| Tokenizer | a BPE port | `ceil(len/4)` + reconciliation | Estimate for admission, actuals for accounting (Pitfall 5) |

**Key insight:** every hard part here (atomicity, exactness, rollover) is already solved by SQLite and `decimal`. The phase's real risk is using them with the wrong default: legacy transactions, half-even rounding, a shared `user_version`.

## Runtime State Inventory

Not a rename/refactor phase, so the section is omitted. One related consequence: adding `max_steps` and `model_prices` **changes `policy_hash` for every policy**. No hashes are persisted outside test tmp dirs, and no `.db` files are tracked [VERIFIED: `ls` of repo root; `runs.db` only ever created under `tmp_path` in tests/test_store.py:58-60]. No data migration is needed.

## Common Pitfalls

### Pitfall 1: TOCTOU over-admission across processes
**What goes wrong:** Concurrent runs (or a run plus a CLI process) each read `spent`, each see headroom, and each reserve.
**Why it happens:** Python's legacy sqlite3 mode opens a transaction only before INSERT/UPDATE/DELETE/REPLACE, never before SELECT [CITED: https://docs.python.org/3/library/sqlite3.html, Cursor.execute: "If autocommit is LEGACY_TRANSACTION_CONTROL, isolation_level is not None, sql is an INSERT, UPDATE, DELETE, or REPLACE statement, and there is no open transaction, a transaction is implicitly opened before executing sql."]. With `isolation_level=None`, "transactions are never implicitly opened" (same page). `Connection.autocommit` is "Added in version 3.12" (same page), and the project supports 3.11, so do not use it.
**Measured (this session, Python 3.12.13 / SQLite 3.53.2, 4 procs × 10 attempts, cap 10):**
```
legacy:    admitted=37 / 39 / 37 (with 1 ms window); 28 / 30 / 20 (no window; one run final_spent=0.600000 after 30 admits)
immediate: admitted=10 in all 6 runs, final_spent=1.000000
```
**How to avoid:** Pattern 2 `_tx`.
**Warning signs:** `admit` contains `with closing(...) as c, c:`, or a SELECT runs before any `BEGIN`.

### Pitfall 2: Tiny costs round to zero
**What goes wrong:** Cheap models and short calls record `0.000000` cost, so the daily budget never trips.
**Measured:** `Decimal(1)*Decimal('0.10')/1000000` gives `1E-7`, `.quantize(Decimal('0.000001'))` gives `0.000000`, and with `rounding=ROUND_CEILING` gives `0.000001` [VERIFIED: venv probe].
**How to avoid:** `cost_of` always uses `ROUND_CEILING`. Test it with 1 token at $0.10/Mtok, expecting `Decimal("0.000001")`.

### Pitfall 3: Reconciling against the wrong day
**What goes wrong:** A call spanning UTC midnight is admitted on day D and reconciled on D+1, so D keeps the estimate and D+1 gets a negative delta.
**How to avoid:** `Admission.utc_date` is the key. Test it with an injected clock that advances across midnight between admit and reconcile.

### Pitfall 4: Negative or bogus provider usage refunds budget
**What goes wrong:** A buggy provider/fake reports `-500` tokens and reconcile *reduces* spend.
**How to avoid:** `Usage.__post_init__` rejects negatives and bools. Treat it as a trust boundary even though it is in-process.

### Pitfall 5: Vacuous tests (mock usage == estimate, or zero usage)
**What goes wrong:** Every reconciliation delta is 0 and every budget is untripped, yet the suite is green (PITFALLS.md Pitfall 6/11).
**How to avoid:** Mock usage is scripted explicitly and non-zero. The end-to-end test asserts `mock.calls` equals the exact number of the call that should have been blocked minus one (call count, not final status).

### Pitfall 6: Schema change breaks existing tests in five places
**What:** Adding two required `Policy` fields fails these Phase 2 tests until they are updated in the **same task**:
- `tests/conftest.py` `_VALID_POLICY` (lines 12-22)
- `tests/test_policy.py` `ALL_FIELDS` (lines 28-38)
- `_HASH_A` / `_HASH_B` YAML literals (lines 157-180). These need `max_steps` and `model_prices` in both, with key/format variation in `_HASH_B` (e.g. `1.0` vs `1.00`)
- `test_hash_changes_when_a_limit_changes` params (lines 193-206). Add `("max_steps", ..., True)` and `("model_prices", ..., True)`
- `test_hashed_key_set_is_pinned` literal set (lines 216-224). Add both names

`tests/test_registry.py` builds policies through the `policy_yaml` fixture [VERIFIED: tests/test_registry.py:132-133], so it is fixed by the conftest change. The conftest serializes each value with `json.dumps` on one line. A nested `model_prices` dict becomes a JSON flow mapping, which is valid YAML, so no fixture rewrite is needed.

### Pitfall 7: `ROLLBACK` masking the real error
**What goes wrong:** `BEGIN IMMEDIATE` times out (`database is locked`), the `except` runs `ROLLBACK`, and that raises "cannot rollback - no transaction is active", hiding the cause.
**How to avoid:** `if c.in_transaction:` guard (Pattern 2).

## Code Examples

### End-to-end early-stop test (success criteria 2 + 4 together)
```python
# tests/test_mock_llm.py -- shape only
def test_runaway_mock_is_stopped_before_the_call(tmp_path, policy_yaml):
    policy = _policy(policy_yaml(max_steps=50, max_tokens_per_run=10_000, max_cost_per_day="0.000200",
                                 model_prices={"mock": {"input_per_mtok": 1, "output_per_mtok": 2}}))
    ledger = SQLiteBudgetLedger(tmp_path / "ledger.db")
    mock = MockLLM([MockTurn(usage=Usage(40, 12, "provider"))], loop=True)
    with pytest.raises(PolicyDenied) as info:
        for _ in range(100):
            adm = ledger.admit("run1", policy, LlmCall("mock", input_tokens=40, max_output_tokens=12))
            ledger.reconcile(adm, mock.complete([]).usage)
    assert info.value.decision.rule == "max_cost_per_day"
    assert mock.calls == EXPECTED_N   # computed from prices; proves the block was PRE-call
```

### Cross-process tests (BUDGET-01 race, BUDGET-03 restart)
Use `subprocess.Popen([sys.executable, "-c", CHILD])`, the pattern already used by `test_hash_is_stable_across_processes` (tests/test_policy.py:231+), rather than `multiprocessing`. A child process importing `eacp.policy` takes 0.21 s wall [VERIFIED: `time` in session], so 4 concurrent children fit in about 0.5 s. **Restart test:** reserve/reconcile in the parent, then a fresh child prints `spent_today(policy_id)`, and the result must equal the parent's value. **Race test:** 4 children × 10 admits against a cap allowing exactly 10 must produce exactly 10 admitted calls. The test discriminates: the legacy pattern failed it in 6/6 probe runs.

### Purity test (POLICY-03)
```python
import ast, pathlib
ALLOWED = {"__future__", "math", "dataclasses", "decimal", "typing", "eacp.policy"}
def test_engine_imports_are_pure():
    tree = ast.parse(pathlib.Path("src/eacp/engine.py").read_text())
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | \
           {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert mods <= ALLOWED, mods - ALLOWED   # no sqlite3/datetime/time/os/framework
```
Resolve the path from `eacp.engine.__file__`, not cwd.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `isolation_level` legacy control | `Connection.autocommit` (PEP 249 style) | Python 3.12 [CITED: docs.python.org sqlite3] | Not usable here (3.11 floor). `isolation_level=None` + explicit BEGIN is the portable equivalent |
| Post-hoc budget check (`finally`/after-kickoff) | Pre-call admission + post-call reconciliation + step ceiling | Project research (PITFALLS.md Pitfall 5) | This phase's core deliverable |

**Deprecated/outdated:**
- PITFALLS.md:180's "Estimate input tokens with `tiktoken` (already a transitive dep)" is false for this lock (`grep tiktoken uv.lock` → no match).
- ARCHITECTURE.md:172's `if ctx.policy.allowed_tools and ...` (empty means allow-all) is superseded by OD-3.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Prices belong in the policy (`model_prices`), and an unpriced model is denied | OD-2 | If the user wants a core price table or "unknown ⇒ token-only enforcement" (FEATURES.md:82 idea), the schema and `decide()` model branch change. Confirm before 03-01 |
| A2 | `allowed_tools: []` = deny-all, no wildcard | OD-3 | Workflows with no tools are unaffected. A user expecting allow-all gets every tool denied (fails safe, loudly) |
| A3 | A "step" = every admitted LLM **or** tool call | BUDGET-04 | If the user means LLM turns only, tool-heavy loops hit the ceiling sooner. One-line change in `decide()` |
| A4 | `ceil(chars/4)` is an adequate pre-call estimate | OD-5 | Underestimates code/CJK, so admission is looser, still bounded to one call by reconciliation |
| A5 | When no `max_output_tokens` is given, the output reservation = the run's remaining tokens | Pattern 1 | Conservative reservations can temporarily block concurrent runs near the daily cap until reconcile |
| A6 | Allow-Decision reports the last rule checked (`allowed_tools` / `max_cost_per_day`) | Pattern 1 | Phase 4 might want all checks recorded. Additive later (a `checks` tuple) |
| A7 | No `require_approval` outcome in Phase 3 | Pattern 1 | Phase 4 widens the Literal. Additive |
| A8 | ASVS mapping below (V5/V11/V12/V7) | Security Domain | Classification only |
| A9 | Currency is unspecified/USD-by-convention; `max_cost_per_day` and prices must share a unit | OD-2 | Document in the policy docs. No code impact |
| A10 | The ledger keys admissions on a caller-supplied `(run_id, call_key)` and keeps reconciled rows, so a replayed call is not charged again (Addendum G-1) | Pattern 2 | If deferred to Phase 5, the `admit()` signature and ledger schema change after Phase 4 builds on them, and TRACE-04 double-counts in the meantime |

## Open Questions

1. **Should one run be able to span policies (re-registration mid-run)?**
   - What we know: `run_usage` is keyed by `run_id`. `daily_spend` is keyed by `policy_id`, so a version bump keeps the same day's spend (desired: same budget line).
   - Recommendation: no handling. A run is admitted against the policy object passed in.
2. **Crash between admit and reconcile.**
   - What we know: the reservation row persists and stays charged at the estimate (fail-safe).
   - Recommendation: leave it charged. `reservations` rows older than a run's end are visible for a later `eacp` diagnostic. No sweeper in v1 (`ponytail:` comment).
3. **Ledger Protocol now or later?** Recommendation: later (see Alternatives). The pattern map suggested one. Choose the concrete class unless the user wants symmetry with `RunStore`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | all | ✓ | 3.12.13 (`.python-version` = 3.12) | — |
| SQLite (linked) | ledger | ✓ | 3.53.2 | — |
| pydantic | policy schema | ✓ | 2.12.5 | — |
| pytest | tests | ✓ | 9.1.1 | — |
| tiktoken | (rejected) | ✗ | — | `ceil(len/4)` heuristic (OD-5) |
| Agent frameworks | not needed this phase | — | — | — |

**Missing dependencies with no fallback:** none. The Intel-Mac CrewAI blocker (STATE.md) does not affect this phase, which is all core.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (pytest-asyncio installed, unused: everything here is sync) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]`: `testpaths=["tests"]`, `--strict-markers`, `filterwarnings=["error::DeprecationWarning"]` |
| Quick run command | `uv run --no-sync pytest -q tests/test_engine.py tests/test_ledger.py tests/test_mock_llm.py tests/test_policy.py` |
| Full suite command | `uv run pytest -q && uv run mypy && uv run ruff check` (mypy reads `strict=true`, `files=["src","tests"]` from pyproject) |
| Baseline | 77 passed in 1.12 s (this session). Phase 3 adds roughly 2 s of subprocess tests |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| POLICY-03 | `decide()` returns a `Decision` with all 6 fields for an allowed and a denied tool call and LLM call; never `bool` | unit | `pytest -q tests/test_engine.py -k decision` | ❌ Wave 0 |
| POLICY-03 | engine.py imports only the stdlib allowlist + `eacp.policy` (no I/O, clock, framework) | unit (AST) | `pytest -q tests/test_engine.py -k pure` | ❌ Wave 0 |
| POLICY-03 | numeric invariant: deny ⇔ observed > limit, parametrized at limit-1/limit/limit+1 for steps, tokens, cost | unit | `pytest -q tests/test_engine.py -k boundary` | ❌ Wave 0 |
| POLICY-03 | forbidden beats allowed; `[]` allowlist denies; unpriced model denied (rule `model_prices`) | unit | `pytest -q tests/test_engine.py -k tools or model` | ❌ Wave 0 |
| BUDGET-01 | over-budget runaway mock stopped **before** the blocking call (`mock.calls` asserted exactly) | integration | `pytest -q tests/test_mock_llm.py -k runaway` | ❌ Wave 0 |
| BUDGET-01 | 4 subprocesses × 10 admits vs cap 10 gives exactly 10 admitted | integration (multi-process) | `pytest -q tests/test_ledger.py -k race` | ❌ Wave 0 |
| BUDGET-02 | reconcile applies `actual - estimate` (scripted usage ≠ estimate); second reconcile raises `KeyError`; cross-midnight reconcile hits the admission date | unit/integration | `pytest -q tests/test_ledger.py -k reconcile` | ❌ Wave 0 |
| BUDGET-03 | spend written by the parent is read back by a fresh subprocess; new UTC date (injected clock) gives a fresh counter; same date different `policy_id` is independent | integration | `pytest -q tests/test_ledger.py -k "restart or rollover"` | ❌ Wave 0 |
| BUDGET-04 | `max_steps` denies the (N+1)th call independently of tokens (huge token/cost limits); tool calls count | unit + integration | `pytest -q tests/test_engine.py tests/test_ledger.py -k steps` | ❌ Wave 0 |
| BUDGET-05 | `Usage` rejects MISSING-with-counts, provider-with-None, negatives, bools; MISSING reconcile charges the estimate (spend unchanged, not 0) and increments `missing_usage` | unit | `pytest -q tests/test_engine.py tests/test_ledger.py -k usage` | ❌ Wave 0 |
| BUDGET-05 | `cost_of` 1 token at $0.10/Mtok gives `Decimal("0.000001")` | unit | `pytest -q tests/test_engine.py -k rounding` | ❌ Wave 0 |
| (schema) | `max_steps`, `model_prices` required; both move the hash; pinned key set updated | unit | `pytest -q tests/test_policy.py` | ✅ (modify) |
| (SC-4) | mock emits scripted tool calls + non-zero usage with no API key env (`monkeypatch.delenv` of `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`, `raising=False`) | unit | `pytest -q tests/test_mock_llm.py` | ❌ Wave 0 |
| (hygiene) | ledger file mode 0600; WAL; bound parameters only | unit | `pytest -q tests/test_ledger.py -k permissions` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** the task's test file + `uv run --no-sync mypy` (strict typing of the frozen dataclasses and the `Decision` Literal is part of correctness)
- **Per wave merge:** `uv run pytest -q && uv run mypy && uv run ruff check`
- **Phase gate:** full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/conftest.py`: add `max_steps` and `model_prices: {"mock": {...}}` to `_VALID_POLICY` (same task as the schema change)
- [ ] `tests/test_engine.py`, `tests/test_ledger.py`, `tests/test_mock_llm.py`: new
- [ ] No framework install needed

## Security Domain

`security_enforcement: true`, ASVS level 1 [VERIFIED: .planning/config.json].

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | library, no users |
| V3 Session Management | no | — |
| V4 Access Control | partial | Tool allow/deny is enforced by `decide()`. Wiring to real callables is Phase 5–7 (TOOLS-01) |
| V5 Input Validation | yes | pydantic `extra="forbid"`, `StrictInt`, `ge=` bounds on new policy fields. `Usage.__post_init__` on usage readings |
| V6 Cryptography | no | (hash is content-addressing, Phase 2) |
| V7 Error Handling/Logging | partial | `PolicyDenied` carries a structured Decision. The audit log is Phase 4 |
| V11 Business Logic | yes | Atomic admission (`BEGIN IMMEDIATE`), step ceiling, fail-closed unknown model, ceiling rounding |
| V12 Files/Resources | yes | Ledger DB 0600 before first connect (copy store.py:179-180) |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Concurrent over-admission (TOCTOU) | Tampering / DoS-of-wallet | `BEGIN IMMEDIATE` around read-decide-write (verified) |
| Negative/forged usage refunding budget | Tampering | `Usage` validation: non-negative ints, not bool |
| Cost rounded to zero | Repudiation of spend | `ROUND_CEILING` |
| Unpriced model as a budget bypass | Elevation | Deny with rule `model_prices` |
| SQL injection via policy_id/run_id/model | Tampering | Bound parameters only (store.py T-02-06 convention). `policy_id` is already pattern-restricted (policy.py:67) |
| Ledger file disclosure (spend, run ids) | Information disclosure | 0600 + WAL sidecars inherit mode (store.py:14-18 rationale) |
| Infinite loop when usage is MISSING | DoS-of-wallet | `max_steps` is independent of token accounting. MISSING is charged at the estimate |

Threat IDs: allocate from one phase-wide sequence (`T-03-NN`) across all plans. Phase 1 reused IDs per plan and had to split them afterwards [VERIFIED: .planning/STATE.md, Phase 1 verify decision].

## Addendum: independent re-verification and one gap (2026-10-05)

A second research pass built its own prototype (`engine.py` / `budget.py` / `mock.py` in a scratch copy of `src/eacp`). Under `mypy --strict` it reported 0 issues and 5/5 prototype tests passed. That prototype confirms the findings above and adds four items the planner should act on.

### G-1 (gap, decide now): replay idempotency of the ledger is not covered above
`.planning/research/PITFALLS.md:153` requires the ledger to be "idempotent by construction. Key every usage record on `(run_id, node_id, call_index)` and `UPSERT`". Line 166 assigns this work to an earlier phase: "with the idempotency-key design settled earlier in the cost/ledger phase" [VERIFIED: read this session]. Pattern 2 above does not settle it, for two reasons:
- `reservation_id` is minted per `admit()`. A LangGraph node that re-runs on resume calls `admit()` again, so its step, tokens and cost are charged twice. That breaks TRACE-04.
- `reconcile()` DELETEs the reservation. Even with a caller-supplied key, a replay *after* reconcile would find no row and charge again.

**Recommendation:** give `admit()` a caller-supplied, deterministic `call_key: str` (Phase 5 derives it from node and call index; Phase 3 tests pass e.g. `"0"`, `"1"`). Make the reservations primary key `(run_id, call_key)`. Under the same `BEGIN IMMEDIATE`, an existing row means an already-admitted call: return its `Admission` and do not charge again. Keep the row at reconcile and set a `reconciled` flag (`UPDATE ... WHERE run_id=? AND call_key=? AND reconciled=0`; rowcount 0 → `KeyError`) instead of DELETE. A double reconcile still raises, and a replay still finds the row.

The prototype ran exactly this (PK `(run_id, call_id)`, prior row → admitted without a charge). Its test admitted `call_id="0"` twice and asserted that `spent_today` equals one charge, and it passed. Doing this now costs one parameter and one column. Doing it in Phase 5 changes the `admit()` signature and the ledger schema after Phase 4's audit code is written against them.
**Test to add:** `test_replayed_admit_is_not_charged_twice`, which runs admit → reconcile → admit with the same key. `spent_today`, `run_usage.steps` and `tokens` must all be unchanged by the second admit.

### G-2: the tempting one-word "fix" for legacy mode also fails
`sqlite3.connect(..., isolation_level="IMMEDIATE")` without `None` looks like it should work, but it stays in legacy mode, so the SELECT still runs outside any transaction. Probe (8 processes × 60 admits, cap = exactly 100 admits): **admitted 107, `in_transaction` after the SELECT = False**. Plain legacy also gave 107 in 2/2 runs, and `isolation_level=None` + `BEGIN IMMEDIATE` gave exactly 100 in 2/2 runs [VERIFIED: executed this session, Python 3.12.13 / SQLite 3.53.2]. This independently corroborates Pitfall 1 at a different scale. Add `isolation_level="IMMEDIATE"` to Pitfall 1's warning signs.

### G-3: `Decision` as a plain dataclass will not JSON-serialize for Phase 4
`json.dumps(dataclasses.asdict(decision))` raises `TypeError: Object of type Decimal is not JSON serializable` [VERIFIED: executed this session]. Keep the frozen dataclass, but render `Decimal` with `str()` in Phase 4's audit writer (or add a `to_json()` helper here) so the result matches the `"0.050000"` form that `policy_hash` uses through pydantic's `mode="json"`. The prototype's alternative (a frozen pydantic `Decision`) gets this for free: `model_dump(mode="json")` gave `{'limit': '0.050000', 'observed': '0.060000', ...}`, and construction cost 3.8 µs. Either is fine. Just don't let Phase 4 discover the problem.

### G-4: cost of connection-per-call in the ledger
The prototype measured admit+reconcile at **2.76 ms per pair** (500 pairs, this Intel Mac, connection per call, 0600 file confirmed). That is negligible next to an LLM call, and consistent with `store.py:191-196`'s accepted ceiling, so no long-lived connection is needed.

### Corrections to citations above
- `03-PATTERNS.md` is cited in Alternatives Considered and Sources, but no such file exists in the phase directory (only `03-RESEARCH.md` and `03-VALIDATION.md`, checked with `ls` this session). Treat those two "03-PATTERNS.md suggestion" rows as unsourced. The recommendations they support (one `PolicyDenied`, no ledger Protocol) stand on their own reasoning.

## Sources

### Primary (HIGH confidence)
- Project source read this session: `src/eacp/policy.py`, `store.py`, `errors.py`, `capabilities.py`, `__init__.py`; `tests/conftest.py`, `test_policy.py`, `test_store.py` (head), `test_registry.py` (grep); `pyproject.toml`; `.github/workflows/*.yml`; `uv.lock` (grep)
- Executed probes (Python 3.12.13, SQLite 3.53.2): 4-process ledger race (legacy vs BEGIN IMMEDIATE, with and without a widened window, 3 runs each); Decimal quantize rounding; nested pydantic `ModelPrice` dump stability and bool rejection; subprocess import latency; baseline test suite (77 passed)
- https://docs.python.org/3/library/sqlite3.html: legacy implicit-transaction rule, `isolation_level=None`, `autocommit` added in 3.12

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` (Pitfalls 5, 6, 11), `ARCHITECTURE.md` (PDP/BudgetLedger split), `SUMMARY.md`, `FEATURES.md`. Project research from 2026-09-24; two claims in it are corrected above
- `.planning/phases/03-.../03-PATTERNS.md`: analog map. This research diverges on Protocol/error-class count, with reasons given

### Tertiary (LOW confidence)
- none

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH. No new dependencies; versions read from the venv
- Architecture: HIGH for locking/rounding/schema mechanics (executed). MEDIUM for the Decision reporting convention (A6) and step definition (A3), which are design choices
- Pitfalls: HIGH. Pitfalls 1, 2 and 6 are measured or read from source

**Research date:** 2026-10-05
**Valid until:** 2026-11-04 (stdlib/SQLite behavior is stable; re-check only if the pydantic pin moves)
