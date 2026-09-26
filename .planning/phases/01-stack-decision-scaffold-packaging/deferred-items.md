# Deferred Items — Phase 01

Out-of-scope discoveries logged during execution. Not fixed; recorded so they are not rediscovered.

| Found in | Item | Why deferred |
|----------|------|--------------|
| 01-01 Task 1 | Global site-packages has `crewai 1.9.3` declaring `uv~=0.9.13` and `openai~=1.83.0`, both already violated (global `openai` is 1.109.1). `pip` warns on every install. | Machine hygiene outside the repo. Does not affect the project venv or any committed artifact. Residue of the earlier `slopcheck install` incident (STATE.md Blockers). Requires the user's decision to prune a global env. |
| 01-01 Task 3 | `prompt.md` is untracked at the repo root although `PROJECT.md` and `CLAUDE.md` both cite it as the authoritative spec. | Pre-existing before this plan; tracking the spec file is a user call, not a Phase 1 deliverable. |
| 01-01 Task 3 | 01-RESEARCH.md's verbatim `__init__.py` docstring contains the literal substring `import langgraph`, which its own plan-level grep gate forbids. Same class of conflict may recur in 01-02's adapter docstrings (which intentionally *do* contain `import ag2` etc. as real code). | Fixed locally by rewording (see 01-01-SUMMARY deviations). The upstream research snippet is unchanged — a future planner writing verify greps over docstrings should anchor them to line start. |
