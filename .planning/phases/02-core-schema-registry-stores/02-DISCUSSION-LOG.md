# Phase 2 Discussion Log

**Date:** 2026-09-27
*Human reference only — not consumed by researcher, planner, or executor.*

## How this discussion was scoped

Four gray areas were identified. The user asked which were worth discussing, so they
were ranked by **reversibility** — how expensive is it to change the default later?

| Area | Cost if the default is wrong | Outcome |
|---|---|---|
| Policy schema strictness | Relaxing required→optional later is non-breaking | Defaulted (D-08) |
| Hash canonicalization | Contained in one function; no stored hashes exist until Phase 4 | Defaulted (D-09) |
| Entrypoint allowlist | Phase 1 precedent + unusually specific requirement text already determine it | Defaulted (D-10) |
| Capability + RunStore shape | **Propagates into all three adapters in Phases 5/6/7** | **Discussed** |

Only the one-way door was discussed. The other three were delegated.

## Q1 — `RunStore` Protocol: sync or async?

**Why it mattered:** ag2's middleware is `async def` throughout (per STACK.md, which
calls `pytest-asyncio` mandatory for exactly this reason); CrewAI's hooks are sync;
LangGraph does both. Whichever shape is chosen, one of the three has to bridge — so the
question is really "who pays, and how much?"

- Options: sync Protocol / async Protocol / sync Protocol plus an async wrapper
- **Selected: sync Protocol**
- Reasoning: SQLite's stdlib driver is sync, so a sync Protocol describes the real I/O
  instead of wrapping it in a false async surface. ag2 pays with one
  `asyncio.to_thread(...)` per call site, contained in its own adapter. The async
  alternative would force CrewAI's sync hooks to drive an event loop, and `asyncio.run`
  inside an already-running loop deadlocks. The "both" option was rejected as a
  premature abstraction — two surfaces and two test suites to save ag2 one line.
- → **D-06**

## Q2 — Where are backend capabilities declared?

**Why it mattered:** WORKFLOW-03 must fail registration when a policy demands a
capability the backend lacks. That rule only works if the capability data is trustworthy,
so the question is where it can least easily go stale.

- Options: per-adapter constant / central registry table / central table plus a
  conformance assertion
- **Selected: per-adapter declaration**
- Reasoning: the declaration sits next to the implementation, so it cannot drift, and it
  extends the `BACKEND` / `FRAMEWORK_VERSION` constant shape Phase 1 already established
  rather than inventing a pattern. A central table is readable offline but can silently
  disagree with the code — the precise failure the AdapterCapabilities decision exists to
  prevent.
- **Consequence surfaced and accepted:** reading capabilities requires importing the
  adapter, so registration needs the matching extra installed, and there is no offline
  way to print the whole matrix. Generate it in CI if docs need it.
- → **D-07**

## Notes

- No scope creep raised; the discussion stayed inside the phase boundary.
- A process defect from Phase 1 was carried into CONTEXT.md as an instruction:
  **allocate Phase 2 threat IDs from one phase-wide sequence.** Phase 1 numbered them
  per-plan and collided `T-01-03` and `T-01-04` across two different threats each.
