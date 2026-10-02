---
phase: 02-core-schema-registry-stores
reviewed: 2026-10-02T18:18:35Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - src/eacp/errors.py
  - src/eacp/capabilities.py
  - src/eacp/policy.py
  - tests/conftest.py
  - tests/test_policy.py
  - pyproject.toml
  - src/eacp/store.py
  - tests/test_store.py
  - src/eacp/registry.py
  - tests/test_registry.py
  - src/eacp/adapters/langgraph_adapter.py
  - src/eacp/adapters/crewai_adapter.py
  - src/eacp/adapters/ag2_adapter.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-10-02T18:18:35Z
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Reviewed `errors.py`, `capabilities.py`, `policy.py`, `store.py`, `registry.py`, the three
adapter placeholders, `pyproject.toml`'s two new config blocks, and all four test files
against the three plans, `02-CONTEXT.md`'s locked decisions, and `02-RESEARCH.md`'s pitfall
register. I independently re-ran `uv run --no-sync pytest -q` (77 passed), `uv run --no-sync
mypy --strict` (clean on 18 source files) and `uv run --no-sync ruff check src tests` (clean)
rather than trusting the SUMMARY files' reported results.

This is a well-built phase. The three documented traps in 02-RESEARCH.md (duplicate-key
override, `model_dump_json()` field-order instability, `set[str]` hash-seed nondeterminism)
are all structurally closed, not just tested around: the duplicate-key constructor compares
*constructed* keys at every mapping-node depth, the hash path goes through `model_dump(mode=
"json")` + `json.dumps(sort_keys=True)` rather than the direct-to-string serializer, and every
hashed collection field is `list[str]` with a sort+dedupe validator. The two PyYAML `# type:
ignore` comments are both narrowly scoped to specific error codes (`import-untyped`, `misc`)
on specific lines, not a blanket suppression. The `Workflow(frozen=True)` deviation is sound:
nothing in this phase or its tests needs to mutate a registered `Workflow`, and leaving it
mutable would let a passed capability/entrypoint gate be invalidated after the fact by
reassigning `entrypoint` or `backend_type` on the stored instance. `registry.py` genuinely
contains zero import machinery (verified by re-reading the file against the AST gate's
`MACHINERY`/`BARE` sets by hand, not just by re-running the test) and reads adapter
`CAPABILITIES` through `eacp.backends.load_backend_module` — a real but *lazily deferred*
import, triggered only inside `register_workflow`, not at `import eacp.registry` time, which
is what keeps module-level import of `registry.py` framework-free. The per-adapter capability
declarations match the required vocabulary and matrix exactly (LangGraph: both; CrewAI/ag2:
`inline_approval` only).

No blocker-level defects were found. Three warnings are worth fixing before this code is
treated as the final word on the trust boundary and the on-disk store; three info items are
minor hardening/quality notes.

## Warnings

### WR-01: T-02-02's byte cap bounds document size, not alias/anchor amplification within it

**File:** `src/eacp/policy.py:25-26, 54-64`
**Issue:** `MAX_POLICY_BYTES = 64 * 1024` is checked against the raw UTF-8 text length
*before* `yaml.load` runs, which correctly blocks a document that is itself too large. It does
**not** bound the size of the Python object graph that a sub-cap document can still expand
into via YAML anchors/aliases. 02-RESEARCH.md's own measurement — 220 bytes of nested anchors
expanding to 531,441 constructed nodes in 0.06s — scales exponentially with nesting depth; a
crafted document using most of the 64KB budget for anchor definitions (rather than the padding
comment `test_oversized_document_rejected` uses to pad past the cap) can still reach
`yaml.load` and blow up memory/CPU well beyond the 531,441-node example, because nothing caps
alias expansion count or depth once the parser is allowed to run.

02-RESEARCH.md frames this as low severity because "the policy file is locally authored", but
02-01-PLAN.md's own trust-boundary table describes the same input as "a file authored outside
the process — possibly by a different team, possibly checked in by a contributor" — a strictly
wider threat surface than "locally authored" implies. The threat register's disposition for
T-02-02 is "mitigate", but the implemented mitigation only closes the size-based instance of
the attack, not the amplification-based one the same finding documents.
**Fix:** Either narrow the threat register's language to state explicitly that amplification
*within* the byte cap is an accepted residual risk for v1 (matching the "locally authored"
framing), or add a cheap structural bound — e.g. reject documents whose anchor/alias count
exceeds a small constant before `construct_mapping` recurses, or set `yaml.SafeLoader`'s (or a
subclass's) `MAX_ALIASES`-style guard if the project later takes contributor-supplied policy
files seriously. A one-line docstring note in `load_yaml_mapping` stating the residual risk
would at minimum prevent a future reader from assuming the byte cap is a complete mitigation.

### WR-02: TOCTOU window between `touch()`, `chmod()`, and `connect()` in `SQLiteRunStore.__init__`

**File:** `src/eacp/store.py:171-186`
**Issue:** `self._path.touch(mode=0o600, exist_ok=True)` followed by `self._path.chmod(0o600)`
followed by `sqlite3.connect(self._path, ...)` are three separate filesystem operations on a
*path*, not on a held file descriptor. If another local process or user with write access to
the same directory swaps the path for a symlink between any of these three calls (classic
CWE-367 TOCTOU), `chmod` and the subsequent writes can land on an unintended file. 02-02-PLAN's
own threat model explicitly scopes the database *path* as trusted application-author input for
v1 ("a caller-supplied database path is not an untrusted input in v1"), so this is not a gap
against this phase's stated threat model — but it is a real, well-known footgun pattern that a
future phase (e.g. once the store path becomes configurable from a CLI flag in Phase 4) could
silently inherit if this constructor is copied forward unexamined.
**Fix:** Open the path with `os.open(path, os.O_CREAT | os.O_RDWR, 0o600)` and operate on the
resulting file descriptor (`os.fchmod`, then hand the fd or a `sqlite3.connect` URI referencing
it) to close the window, or at minimum leave a comment flagging the assumption so it doesn't
silently graduate into a context where the path is attacker-influenced.

### WR-03: `Policy.version` has no floor, accepting zero or negative version numbers

**File:** `src/eacp/policy.py:80`
**Issue:** `version: StrictInt` has no `Field(ge=...)` constraint, unlike `max_tokens_per_run`
(`ge=1`) and `max_cost_per_day` (`ge=Decimal(0)`). A policy document with `version: 0` or
`version: -1` is accepted and will be written verbatim into every run record's `policy_id`
pairing (policy_hash excludes it, but the `runs.policy_id`/`version` pairing is still
semantically meaningful for an operator reading history). This is a minor inconsistency with
the rest of the schema's "every numeric field is bounded" posture rather than a functional
defect — nothing in Phase 2 currently compares versions ordinally.
**Fix:** Add `Field(ge=1)` to `version` for consistency, or document explicitly why version
numbers are unconstrained (e.g. if a future phase wants to support `version: 0` as a draft
marker).

## Info

### IN-01: `_PolicyId` is a private (underscore-prefixed) type imported across a module boundary

**File:** `src/eacp/registry.py:24, 57`
**Issue:** `registry.py` does `from eacp.policy import Policy, _PolicyId` and uses `_PolicyId`
to type `Workflow.policy_id`. `_PolicyId`'s leading underscore signals "module-private" by
Python convention, so importing and reusing it in a sibling module is a minor encapsulation
leak — a future edit to `policy.py` that renames or removes `_PolicyId` (believing it to be
internal, since nothing marks it as part of the public surface) will silently break
`registry.py` with no `__all__`-based signal that it was depended upon externally.
**Fix:** Either promote the pattern to a public name (`PolicyId`, documented as shared) or
duplicate the one-line `Annotated[str, Field(pattern=...)]` in `registry.py` so the two modules
don't share a "private" symbol.

### IN-02: Known-context framing of the CAPABILITIES-reading mechanism vs. actual implementation

**File:** `src/eacp/registry.py:21, 105`
**Issue:** No code defect — noted for reviewer-to-reviewer clarity. The registry reads adapter
`CAPABILITIES` via a genuine (but lazily deferred) `importlib.import_module` call inside
`eacp.backends.load_backend_module`, triggered only when `register_workflow` runs for a given
backend — not via static AST parsing of the adapter source. AST parsing is used only by the
test suite (`tests/test_registry.py::test_registry_has_no_import_machinery` and Task 1's
plan-time verify script) to inspect the three adapter files' `CAPABILITIES` declarations
*without* importing them, since the frameworks aren't installed in the core-only dev/CI
environment. `import eacp.registry` itself stays framework-free because the import is deferred
into a function body, not because the registry avoids importing adapters altogether.
**Fix:** None required; flagging only so the distinction between "framework-free at module
import time" (true, by deferral) and "never imports adapters at all" (false — it does, lazily)
doesn't get conflated in later documentation.

### IN-03: Registry gate 2 (known backend name) is effectively unreachable given current schema validation

**File:** `src/eacp/registry.py:101-104`
**Issue:** `register_workflow` checks `workflow.backend_type not in available_backends()` as
its second gate, but `Workflow.backend_type` is already typed as the `BackendType` `Literal`,
which `test_backend_literal_matches_backends_module` pins equal to `available_backends()`. Any
`Workflow` built via the normal `Workflow.model_validate(...)` path has already had
`backend_type` restricted to one of the three known names, so this gate can only fire if a
caller bypasses validation (e.g. `Workflow.model_construct(...)`), which nothing in this phase
does. This is intentional defense-in-depth per the plan's three-gate design, not a bug, but
worth naming so a future refactor doesn't mistake dead-in-practice code for a genuine runtime
check against `available_backends()` drift.
**Fix:** None required; consider a one-line comment noting the gate is defense-in-depth against
non-`model_validate` construction paths, since the Literal already enforces this for the normal
path.

---

_Reviewed: 2026-10-02T18:18:35Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
