# Phase 1: Stack Decision, Scaffold & Packaging - Context

**Gathered:** 2026-09-25
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers an installable Python package (`eacp`) whose core has zero agent-framework dependencies, with each framework adapter available as an optional, lazily-imported extra (`eacp[langgraph]`, `eacp[crewai]`, `eacp[ag2]`), a committed lockfile for reproducible installs, a CI matrix that gates the zero-framework-core property from commit one, and README documentation of the known platform limitation (macOS x86_64 / CrewAI's `lancedb` dependency has no wheel there). It does not implement any policy, workflow, or adapter logic — that starts in Phase 2. Requirements: PACKAGE-01, PACKAGE-02, PACKAGE-03, PACKAGE-04.

</domain>

<decisions>
## Implementation Decisions

### Project naming & branding
- **D-01:** Package/import/CLI name is `eacp` (as already used throughout REQUIREMENTS.md and ROADMAP.md). The local working-directory name (`Self-ReflectiveAgentwithAuto-Eval`) is cosmetic and does not need to match — it never appears in the published package, PyPI name, or CLI invocation. No rename needed.

### Repository layout
- **D-02:** Use `src/` layout: package source lives at `src/eacp/`, tests at `tests/`. Chosen over a flat `eacp/`-at-root layout specifically to prevent accidentally importing an uninstalled source tree instead of the installed package — relevant here because multiple framework extras with lazy imports make that failure mode easy to hit silently.
- **D-03:** `examples/`, `docs/`, and `benchmarks/` (per prompt.md's module layout) live at repo root, siblings to `src/`, `tests/`, and the existing `LICENSE`.

### CI
- **D-04:** Stand up GitHub Actions CI in this phase, not deferred. Minimum: a 4-job matrix — `core` (installs with zero framework extras, asserts `import eacp` succeeds and no LangGraph/CrewAI/ag2 packages are present) plus one job per adapter extra (`eacp[langgraph]`, `eacp[crewai]`, `eacp[ag2]`) installing and importing cleanly. The `core` job gates every push — this is the mechanism that keeps the project's central credibility claim (framework-free core) true over time rather than asserted once and silently rotting.
- **D-05:** CI matrix should account for the known macOS x86_64 / `lancedb` install failure (from research/STACK.md) — run on `ubuntu-latest` (and optionally `macos-latest` which GitHub Actions runs on Apple Silicon, not Intel) rather than an Intel-Mac runner that would fail for reasons unrelated to this project's code.

### Claude's Discretion
- Exact `pyproject.toml` structure, dependency-group/extras syntax, and lockfile tool invocation (`uv`, per research/STACK.md) — implementation detail, not a user-facing decision.
- Exact CI YAML structure (job names, caching strategy, matrix syntax) beyond the 4-job core+3-extras requirement above.
- Whether to also test on Windows — not raised during discussion; default to Linux + macOS (arm64) unless research/planning surfaces a reason to add Windows.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source spec
- `prompt.md` (repo root) — original full target spec: module layout (`core/engine/`, `framework_adapters/`, `observability/`, `evaluation/`, `examples/`, `docs/`), code style (Python 3.11+, type hints), output format expectations

### Project planning
- `.planning/PROJECT.md` — core value, constraints, key decisions (ag2 over autogen, real libraries not stubs, SQLite pluggable store, mock-LLM-first)
- `.planning/REQUIREMENTS.md` §PACKAGE — the 4 requirements this phase must satisfy, plus full v1 scope for context on what later phases will need this scaffold to support
- `.planning/ROADMAP.md` §Phase 1 — phase goal, success criteria, dependency note on why this project uses 10 horizontal-layer phases instead of the 4-6 a "standard" granularity would typically imply

### Research (all written 2026-09-24, verified against live PyPI/wheels — treat as current, not training-data knowledge)
- `.planning/research/STACK.md` — exact package versions and pins to scaffold against: `ag2>=1.1,<2`, `langgraph>=1.2,<1.3`, `crewai>=1.15,<2`, `pydantic>=2.11,<2.13` (hard cap from crewai-core), `uv` for lockfile/dep management, platform matrix (macOS x86_64 fails via `lancedb`)
- `.planning/research/PITFALLS.md` — Pitfall 1 (AutoGen package confusion — module must be named `ag2_adapter.py`, never `autogen_adapter.py`) and Pitfall 2 (monolithic dependency environment — 155 packages if not split into extras) both land squarely in this phase
- `.planning/research/SUMMARY.md` §Phase 1 — "Delivers" and "Exit" criteria this phase was originally scoped against

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
None — repo is greenfield (LICENSE + prompt.md only at project start; no prior Python code, no existing package structure).

### Established Patterns
None yet established — this phase establishes the first patterns (layout, extras structure, CI) that all later phases build on.

### Integration Points
N/A for this phase — it has no upstream code to integrate with. It is itself the integration point every later phase (2 through 10) builds on.

</code_context>

<specifics>
## Specific Ideas

No specific UI/behavior references — this is a packaging/infrastructure phase with no user-facing surface beyond `pip install` and CI status.

</specifics>

<deferred>
## Deferred Ideas

None raised during discussion — stayed within phase scope (naming, layout, CI timing).

</deferred>

---

*Phase: 1-Stack Decision, Scaffold & Packaging*
*Context gathered: 2026-09-25*
