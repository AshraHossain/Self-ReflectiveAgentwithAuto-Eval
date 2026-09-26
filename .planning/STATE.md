---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 01-02-PLAN.md
last_updated: "2026-09-26T18:56:02.305Z"
last_activity: 2026-09-26 -- Completed plan 01-02 (lazy backend loader, three adapter placeholders, packaging tests; langgraph+ag2 extras realized locally)
progress:
  total_phases: 10
  completed_phases: 0
  total_plans: 3
  completed_plans: 2
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-24)

**Core value:** A single policy definition can govern a workflow regardless of which framework (LangGraph, CrewAI, or ag2) executes it — enforced for real, not just documented.
**Current focus:** Phase 1 — Stack Decision, Scaffold & Packaging

## Current Position

Phase: 1 (Stack Decision, Scaffold & Packaging) — EXECUTING
Plan: 3 of 3
Status: Ready to execute
Last activity: 2026-09-26 -- Completed plan 01-02 (lazy backend loader, three adapter placeholders, packaging tests; langgraph+ag2 extras realized locally)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 2
- Average duration: 12min
- Total execution time: 24min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 01 P01 | 1 | 14min (3 tasks, 9 files) | 14min |
| Phase 01 P02 | 1 | 10min (3 tasks, 7 files) | 10min |

**Recent Trend:**

- Last 5 plans: 14min, 10min
- Trend: ↓ faster

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Init: AutoGen-lineage adapter targets `ag2` (not `autogen`/`pyautogen`/`autogen-agentchat`) — actively maintained, governance-friendly middleware/observer/hitl_hook API; `ag2.network` multi-agent ergonomics unproven, flagged for a Phase 7 spike with `autogen==0.14.x` as documented fallback
- Init: Horizontal-layers roadmap structure chosen over vertical MVP slices — matches research's real dependency order (approval gate must exist before any adapter; adapters built one at a time, not in parallel)
- Init: Cross-adapter conformance suite added to v1 scope (Phase 7); dry-run/shadow mode, per-tenant policy scoping, and the control-plane-overhead benchmark reframe deferred to v2
- Init: Uniform durable pause/resume across all three frameworks is architecturally impossible (LangGraph=durable, ag2=snapshot, CrewAI=blocking) — resolved via a declared `AdapterCapabilities` matrix that fails loudly at registration rather than faking parity
- [Phase 1]: 01-01: Omitted the `local` extra from pyproject.toml (01-RESEARCH.md Q2) — it pins langchain-ollama and ag2[ollama] that nothing uses yet; it ships with the phase that builds Ollama support
- [Phase 1]: 01-01: Upgraded the pip-installed uv 0.9.30 in place to 0.12.19 to match the CI UV_VERSION pin — a standalone 0.12.19 existed at ~/.local/bin but PATH put the stale pip copy first, so bare `uv` would have written a lockfile with the wrong revision format
- [Phase 1]: 01-01: pyproject.toml, README.md and src/eacp/__init__.py are kept literally free of the tokens `autogen`, `import langgraph` and `from eacp.adapters` so the anti-regression greps stay true gates instead of waived checks
- [Phase 1]: 01-02: FRAMEWORK_VERSION reads importlib.metadata.version() instead of the researched getattr(framework, '__version__') pattern — langgraph 1.2.12 exposes no __version__ and the pattern silently reported 'unknown'; the except PackageNotFoundError guard is required because that error subclasses ModuleNotFoundError and would otherwise make load_backend_module misreport an installed framework as a missing extra
- [Phase 1]: 01-02: eacp.backends is the package's only importlib.import_module site and the _BACKENDS allowlist lookup runs before it, so a caller-supplied backend name is never interpolated into an import target (T-01-04, Phase 2 WORKFLOW-02 seed)
- [Phase 1]: 01-02: autogen gates are scoped to filenames, backend keys and pyproject.toml — never raw text in src/ — so ag2_adapter.py's docstring stays free to name the three distributions it is not

### Pending Todos

None yet.

### Blockers/Concerns

- The `gsd-roadmapper` subagent stalled 3 times in a row (rate limit once, then two "no progress for 600s" watchdog kills on both opus and sonnet) when asked to produce a Horizontal Layers roadmap — its own baked-in agent instructions (`~/.claude/agents/gsd-roadmapper.md`) contain a hardcoded "never use horizontal layers" anti-pattern that directly contradicts that instruction. ROADMAP.md/STATE.md/REQUIREMENTS.md traceability were written directly instead, using research/SUMMARY.md's already-detailed phase plan as the source. Future roadmap revisions for this project should account for this — the roadmapper agent may need the anti-pattern instruction addressed upstream (in `~/.claude/agents/gsd-roadmapper.md`) before it can be trusted for this project's structure again.
- Phase 7 (ag2 adapter) is flagged by research as needing a code spike before adapter design is locked — `ag2.network` multi-agent ergonomics is ~2 months old and unproven for a 3-agent conversation.
- Phase 6 (CrewAI) has open questions on async `request_human_input` safety and whether `after_llm_call` exposes token usage directly — needs a code spike, not more research.
- The repo-root spec file was originally `prompt,md` (comma); at some point during research a subagent renamed it to `prompt.md` (period) without being asked to — an unauthorized but low-risk/non-destructive filesystem change. All doc references (PROJECT.md, CLAUDE.md) have been corrected to `prompt.md`, matching the file as it now exists on disk.
- **Resolved:** The Phase 1 `gsd-phase-researcher` agent ran `slopcheck install` (not `scan`) while checking package legitimacy, which pip-installed packages into the user's *global* site-packages (not a project venv), clobbering 4 existing packages (langchain-core, openai, orjson, typing_extensions — repaired by the agent) and leaving ~20 residual packages behind (langgraph*, ag2, langchain-protocol, ormsgpack, sqlite-vec, librt, fast-depends, trove-classifiers, plus an undisclosed second batch: slopcheck, ast_serialize, mypy, pytest, pytest-asyncio, ruff, hatchling, iniconfig, pathspec, pluggy, tomlkit). Both batches were fully uninstalled and the global environment verified clean (langchain imports correctly, `pip check` shows only pre-existing unrelated warnings). **Root cause: the gsd-phase-researcher agent's protocol text prescribes `slopcheck install` for package-legitimacy checks, which is destructive — it should prescribe `slopcheck scan` instead.** This is the same class of issue as the roadmapper's contradictory anti-pattern instruction (see above) — a baked-in GSD agent instruction causing real harm. Worth fixing upstream in whichever agent definition/skill carries this protocol text.
- **Real (unfixable) local dev constraint discovered:** this development machine is a genuine Intel Mac (x86_64). CrewAI's `lancedb` dependency has never published, and cannot get, a macOS x86_64 wheel or sdist — verified across versions 0.29.0–0.39.0. This means **Phase 6 (CrewAI adapter) can never be developed/tested directly on this machine**, only via CI or a Linux environment. User decided: develop/test Phase 6 inside a Docker/colima container on this machine. This should be set up as a Phase 6 prerequisite, not discovered mid-phase.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Scope | Dry-run/shadow policy mode | v2 | Requirements (2026-09-24) |
| Scope | Control-plane overhead benchmark | v2 | Requirements (2026-09-24) |
| Scope | Per-tenant policy scoping | v2 | Requirements (2026-09-24) |
| Scope | Durable approval on CrewAI/ag2 | v2 (framework limitation) | Requirements (2026-09-24) |

## Session Continuity

Last session: 2026-09-26T18:56:02.294Z
Stopped at: Completed 01-02-PLAN.md
Resume file: .planning/phases/01-stack-decision-scaffold-packaging/01-03-PLAN.md
