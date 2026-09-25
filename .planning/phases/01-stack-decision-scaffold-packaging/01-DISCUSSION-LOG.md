# Phase 1: Stack Decision, Scaffold & Packaging - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-25
**Phase:** 1-Stack Decision, Scaffold & Packaging
**Areas discussed:** Project naming & branding, Repository layout, CI setup

---

## Project naming & branding

| Option | Description | Selected |
|--------|-------------|----------|
| Keep pip name 'eacp', ignore dir name | Package imports as `eacp`, CLI is `eacp`, PyPI name (if ever published) is `eacp` — the local folder name is cosmetic | ✓ |
| Rename the repo folder too | Rename working directory (and eventually a GitHub repo) to match package name before scaffolding | |
| Let me pick a different package name | Use a name other than `eacp` | |

**User's choice:** Keep pip name 'eacp', ignore dir name (Recommended option).
**Notes:** Repo directory name (`Self-ReflectiveAgentwithAuto-Eval`) is unrelated to EACP branding but doesn't appear in the published artifact, so no rename needed.

---

## Repository layout

| Option | Description | Selected |
|--------|-------------|----------|
| src/ layout | `src/eacp/` for the package, `tests/` alongside — standard modern Python packaging convention | ✓ |
| Flat layout | `eacp/` directly at repo root next to `examples/`, `docs/`, `benchmarks/` | |

**User's choice:** src/ layout (Recommended option).
**Notes:** Chosen specifically to prevent accidentally importing an uninstalled source tree instead of the installed package — relevant given multiple framework extras with lazy imports.

---

## CI setup

| Option | Description | Selected |
|--------|-------------|----------|
| Set up CI now | GitHub Actions workflow in Phase 1 alongside packaging | ✓ |
| Defer CI, document only | README documents platform/install matrix; CI YAML comes later | |

**User's choice:** Set up CI now (Recommended option).
**Notes:** Catches the "core imports with zero frameworks" regression from commit one — the credibility-critical property of the whole project.

---

## Claude's Discretion

- Exact `pyproject.toml` structure, extras/dependency-group syntax, lockfile tool invocation (`uv`)
- Exact CI YAML structure (job names, caching, matrix syntax) beyond the 4-job core+3-extras shape
- Whether to test on Windows — defaulted to Linux + macOS (arm64) only, not raised during discussion

## Deferred Ideas

None — discussion stayed within phase scope.
