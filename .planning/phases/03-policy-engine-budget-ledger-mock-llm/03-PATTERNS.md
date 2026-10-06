# Phase 3: Policy Engine, Budget Ledger & Mock LLM - Pattern Map

**Mapped:** 2026-10-05
**Files analyzed:** 10 (5 new, 5 modified)
**Analogs found:** 9 / 10 (`mock_llm.py` has only a partial analog)

All analog paths below are git-tracked (`git ls-files src tests`).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/eacp/engine.py` (NEW) | pure service | transform | `src/eacp/store.py` (frozen dataclasses, Literal aliases) + `src/eacp/policy.py` (Decimal quantize) | partial (role differs, idioms exact) |
| `src/eacp/ledger.py` (NEW) | store | CRUD, cross-process | `src/eacp/store.py` `SQLiteRunStore` | exact role, **deliberate transaction divergence** |
| `src/eacp/mock_llm.py` (NEW) | utility | request-response (scripted) | `src/eacp/store.py` dataclasses only | partial; use RESEARCH Pattern 3 |
| `src/eacp/policy.py` (MOD) | model / trust boundary | validation | itself (lines 67-107) | exact |
| `src/eacp/errors.py` (MOD) | utility | — | itself | exact |
| `tests/conftest.py` (MOD) | test fixture | — | itself (lines 12-22) | exact |
| `tests/test_policy.py` (MOD) | test | — | itself | exact |
| `tests/test_engine.py` (NEW) | test | unit | `tests/test_policy.py` (parametrize tables) | role-match |
| `tests/test_ledger.py` (NEW) | test | integration, multi-process | `tests/test_store.py` + `tests/test_policy.py:231-251` (subprocess) | exact |
| `tests/test_mock_llm.py` (NEW) | test | integration | `tests/test_store.py` | role-match |

## Pattern Assignments

### `src/eacp/engine.py` (pure service, transform)

**Analog:** `src/eacp/store.py` lines 21-34, 44-65 for module header/dataclass style; `src/eacp/policy.py` lines 90-97 for Decimal quantizing.

**Imports/header** (store.py 21-30) — copy `from __future__ import annotations` + stdlib-only imports. Engine allowlist is narrower: `__future__, math, dataclasses, decimal, typing, eacp.policy` only (AST purity test). No `datetime`, no `sqlite3`.

**Literal alias pattern** (store.py 32-34):
```python
# `denied` is a governance halt (approval refused, APPROVAL-03; budget block, BUDGET-01), which
# is a different outcome from `failed`, a crash.
RunStatus = Literal["running", "awaiting_approval", "succeeded", "failed", "denied"]
```
Apply to `UsageSource`, `Rule`, `Decision.outcome`. Comment the "why" above the alias.

**Record pattern** (store.py 44-54):
```python
@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    ...
    metrics: Mapping[str, object]
```
Use for `Decision`, `LlmCall`, `ToolCall`, `BudgetState`, `Usage`. `Usage.__post_init__` validation is new (no analog has `__post_init__`); raise `ValueError`, matching policy.py validators' error type.

**Decimal pattern** (policy.py 90-97):
```python
    def _quantize(cls, v: Decimal) -> Decimal:
        # Quantize, never normalize: Decimal("100").normalize() serializes as "1E+2".
        try:
            return v.quantize(_COST_EXP)
        except InvalidOperation:
            raise ValueError("cost is out of range") from None
```
**Divergence:** `cost_of` must pass `rounding=ROUND_CEILING` (RESEARCH Pitfall 2); the policy validator keeps default rounding. Import `COST_EXP` (renamed public) from `eacp.policy` — do not define a second constant.

Core body: RESEARCH.md Pattern 1 (lines 170-274) verbatim.

---

### `src/eacp/ledger.py` (store, CRUD cross-process)

**Analog:** `src/eacp/store.py` `SQLiteRunStore` (lines 168-284).

**Module docstring** (store.py 1-19): copy the WAL/three-files/0600 explanation, re-pointed at `ledger.db`. Add: why `BEGIN IMMEDIATE` (cite the race probe).

**Constructor — COPY** (store.py 171-189):
```python
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.touch(mode=0o600, exist_ok=True)
        self._path.chmod(0o600)
        with closing(self._connect()) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(_SCHEMA)
            # ponytail: migrations are a user_version comparison + if-ladder ...
            c.execute("PRAGMA user_version=1")
```
Add keyword `clock: Callable[[], datetime] = lambda: datetime.now(UTC)` (store.py 39-41 `utc_now` is the precedent for `datetime.now(UTC)`). Setup may use a plain `sqlite3.connect(self._path, timeout=30.0)` via `closing`; no `foreign_keys` pragma needed (schema has no FKs).

**Transactions — DO NOT COPY** store.py 207-208 / 228-234:
```python
        with closing(self._connect()) as c, c:   # legacy implicit tx: over-admits 2-4x
```
**Divergence (deliberate, measured):** `admit`/`reconcile` use the `_tx()` contextmanager from RESEARCH.md lines 311-329 (`isolation_level=None`, `BEGIN IMMEDIATE`, `ROLLBACK` only `if c.in_transaction`). Read-only helpers (`spent_today`, `run_usage`) may keep store.py's `with closing(self._connect()) as c:` read style (store.py 254-257).

**Unknown-id error — COPY** (store.py 233-234):
```python
            if cur.rowcount == 0:  # a silent no-op on an unknown id is worse than a raise
                raise KeyError(f"unknown run_id {run_id!r}")
```
Use for `DELETE FROM reservations WHERE reservation_id=?` in `reconcile` (double-reconcile -> `KeyError`).

**Bound params** (store.py 262-264, T-02-06 comment): every value `?`-bound; money stored as `str(Decimal)`, dates as `date.isoformat()` — never a `datetime`/`date` object (store.py 9-12; `error::DeprecationWarning`).

**ponytail comment convention** (store.py 187-196): add one for "no reservation sweeper in v1" and the one-connection-per-call rationale.

**Divergence:** no `BudgetLedger` Protocol (store.py 68-108 has `RunStore` Protocol). Concrete class only, per RESEARCH Alternatives. Separate DB file from `runs.db` (both set `user_version=1`).

---

### `src/eacp/mock_llm.py` (utility, scripted)

**Analog:** none for behavior. Dataclass style from store.py 44-54. Use RESEARCH.md Pattern 3 (lines 342-374). Must stay framework-free (`tests/test_packaging.py:26` guards `import eacp`; mock_llm imports only stdlib + `eacp.engine`).

---

### `src/eacp/policy.py` (MOD)

**Analog:** itself.
- Rename `_COST_EXP` (line 28) -> `COST_EXP`; update line 95.
- Add `_ModelName` next to `_PolicyId` (line 67):
```python
_PolicyId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
```
  widened with `:` and `/`.
- `ModelPrice(BaseModel)` copies `model_config = ConfigDict(extra="forbid", frozen=True)` (line 77) and the `_quantize` validator (lines 90-97). Prefer reusing one module-level helper over duplicating the body.
- Add to `Policy` field block (lines 79-88): `max_steps: Annotated[StrictInt, Field(ge=1)]` (copy line 81 style) and `model_prices: dict[_ModelName, ModelPrice]`. Both content (hashed) — `_IDENTITY_FIELDS` (line 113) unchanged.
- `policy_hash` (121-135) unchanged; nested dump verified hash-stable.

---

### `src/eacp/errors.py` (MOD)

**Analog:** itself (lines 1-14), one-line docstring classes:
```python
class CapabilityError(ValueError):
    """A workflow's policy requires a capability its backend does not provide."""
```
**Divergence:** `PolicyDenied` carries data. Base `Exception` (it's not a bad value), `__init__(self, decision: Decision)` storing `self.decision`, message from `decision.rule/limit/observed`. Import `Decision` under `TYPE_CHECKING` to avoid errors.py -> engine.py -> policy.py -> errors.py cycle (policy.py line 21 imports errors).

---

### `tests/conftest.py` (MOD)

Lines 12-22 `_VALID_POLICY`: add `"max_steps": 10` and `"model_prices": {"mock": {"input_per_mtok": 1, "output_per_mtok": 2}}`. `json.dumps` per key (line 35) emits a flow mapping — valid YAML, no fixture rewrite.

### `tests/test_policy.py` (MOD) — same task as schema change

- `ALL_FIELDS` lines 28-38: add both.
- `_HASH_A` / `_HASH_B` lines 157-180: add both; vary format in B (`1.0` vs `1.00`, key order inside `model_prices`).
- params lines 193-206: add `("max_steps", 11, True)`, `("model_prices", {...}, True)`.
- pinned set lines 218-226: add both names.

### `tests/test_engine.py` (NEW)

**Analog:** `tests/test_policy.py` 193-211 (parametrize table with ids-by-tuple):
```python
@pytest.mark.parametrize(
    ("field", "new_value", "moves_hash"),
    [ ("max_tokens_per_run", 101, True), ... ],
)
def test_hash_changes_when_a_limit_changes(field: str, new_value: Any, moves_hash: bool) -> None:
```
Use for the limit-1/limit/limit+1 boundary invariant. Build policies with `_policy(text)` helper (test_policy.py 183-184) or `Policy.model_validate(load_yaml_mapping(policy_yaml(...)))`. AST purity test: RESEARCH lines 489-498, path from `eacp.engine.__file__`.

### `tests/test_ledger.py` (NEW)

**Analog:** `tests/test_store.py`.
- Module docstring + real file under `tmp_path`, never `:memory:` (test_store.py 1-6).
- Fixture (test_store.py 58-60): `SQLiteBudgetLedger(tmp_path / "ledger.db")`.
- Reopen + PRAGMA checks (160-168), 0600 + sidecars with a held connection (222-234) — copy both nearly verbatim.
- Subprocess pattern (test_policy.py 231-251):
```python
    digests = {
        subprocess.run(
            [sys.executable, "-c", child],
            input=blob, capture_output=True, text=True, check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout.strip()
        for seed in ("0", "1", "2", "3")
    }
```
  Restart test: `subprocess.run` as-is. Race test: diverge to `subprocess.Popen` x4 started before any `wait()`, so they actually contend; each child prints its admitted count; assert sum == 10.
- Clock injection: pass `clock=lambda: <fixed datetime>` mutated via a list/closure for the cross-midnight test; no sleeping.

### `tests/test_mock_llm.py` (NEW)

**Analog:** test_store.py structure. Early-stop shape: RESEARCH lines 471-483 — assert `mock.calls` exact. Key-free: `monkeypatch.delenv("OPENAI_API_KEY", raising=False)` etc.

## Shared Patterns

### Money / Decimal
**Source:** `src/eacp/policy.py` 28, 90-97. **Apply to:** engine, ledger, policy. Decimal only, stored as TEXT `str(Decimal)`; quantize to `COST_EXP`; `ROUND_CEILING` for computed cost.

### SQLite hygiene
**Source:** `src/eacp/store.py` 171-189, 197-203, 262-264. **Apply to:** ledger. 0600 before first connect, WAL first statement, `timeout=30.0`, `row_factory = sqlite3.Row`, bound params only, ISO strings not datetimes.

### Errors
**Source:** `src/eacp/errors.py`; store.py 233-234 (`KeyError` on unknown id). Validation errors raise `ValueError`; governance deny raises `PolicyDenied`.

### Core import discipline
**Source:** `src/eacp/__init__.py` docstring; `tests/test_packaging.py:26`. **Apply to:** all three new modules — no framework imports; do not add re-exports to `__init__.py`.

### Typing
`mypy --strict` over src+tests: annotate every test function `-> None` (as test_store.py / test_policy.py do).

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `src/eacp/mock_llm.py` (behavior) | utility | scripted | No scripted/fake components exist yet; use RESEARCH.md Pattern 3 |
| `ledger._tx` | store helper | cross-process tx | Codebase has no explicit-transaction code; store.py's style is the anti-pattern here. Use RESEARCH.md lines 311-329 |

## Metadata

**Analog search scope:** `src/eacp/`, `tests/`
**Files scanned:** 13 tracked
**Pattern extraction date:** 2026-10-05
