# Roadmap

## Current State

- Baseline runtime and tests: Python 3.11+, MCP server (`python -m gwt_context`), and `pytest` baseline of 108 passing tests.
- Architecture baseline is established in `ARCHITECTURE.md`; active work is P5/P6 boundary migration.
- Benchmark entrypoints are present and runnable:
  - `python -m tests.benchmarks.ruler_multi_hop`
  - `python -m tests.benchmarks.longbench_pro`
- Task onboarding constraint is required in both `AGENTS.md` and task planning:
  - read `ARCHITECTURE.md` first,
  - record in/out boundaries, forbidden imports, and forbidden coupling checks,
  - include explicit pass/fail acceptance before implementation.
- Architecture-boundary checks must be rerun after implementation:
  - application code should consume interfaces from `interfaces/ports.py`,
  - MCP handlers should use only declared tool/resource contracts,
  - task logs must record each check as pass/fail in the task plan.

## Short-term

### 2026-04-22 — P7 benchmark harness hardening
- **Owner:** infra + platform
- **Inputs:** `tests/benchmarks/*.py`, `.env.example`, `tests/benchmarks/config.py`, `pyproject.toml`
- **Scope:** remove setup flakiness and make benchmark execution deterministic for local and CI runs.
- **Acceptance:**
  - Both benchmark entrypoints run with exit code `0` in smoke mode.
  - `.[bench]` dependencies install cleanly and `python -m tests.benchmarks.ruler_multi_hop --max-tasks 1` emits JSON under `tests/benchmarks/results/`.
  - `.env.example` variables remain loadable by benchmark config without code edits.

### 2026-04-26 — P5 port migration starter in application layer
- **Owner:** application architecture
- **Inputs:** `src/gwt_context/application/*`, `src/gwt_context/interfaces/ports.py`, `src/gwt_context/server.py`
- **Scope:** convert concrete infra construction/usage in `application/` to port-backed dependencies where currently blocking.
- **Acceptance:**
  - Constructor dependencies for application classes use interfaces from `interfaces/ports.py` where feasible.
  - No forbidden import from `application/` to concrete infra modules added in new changes.
  - `pytest` remains green with no regression in `tests/unit` and `tests/integration`.

### 2026-04-30 — P6 MCP boundary refinement (tools/resources)
- **Owner:** MCP/application integration
- **Inputs:** `src/gwt_context/mcp/tools.py`, `src/gwt_context/mcp/resources.py`, `tests/unit/test_mcp_tools.py`
- **Scope:** remove remaining direct-state coupling, keep tool contracts stable.
- **Acceptance:**
  - MCP handlers consume only port-defined interfaces or declared application services.
  - New/updated delegation tests cover `gwt_query`, `gwt_compete`, `gwt_link`, and resource read paths.
  - `pytest` remains green with no regression in MCP payload behavior.

## Medium-term

### 2026-05-07 — P2 complete P5 migration in core application layer
- **Owner:** core app
- **Inputs:** `src/gwt_context/application/goal_manager.py`, `cycle.py`, `ingestion.py`
- **Scope:** finish port migration for all remaining concrete-implementation dependencies.
- **Acceptance:**
  - Application services can be instantiated with test doubles only through ports.
  - New boundary tests assert no direct imports from application classes to concrete infra adapters.
  - No changes in visible MCP payload shapes.

### 2026-05-14 — P2 complete P6 MCP cleanup
- **Owner:** MCP boundary
- **Inputs:** `src/gwt_context/mcp/*`, `src/gwt_context/application/*`
- **Scope:** close remaining internal-state coupling and expose explicit read-model DTO boundaries.
- **Acceptance:**
  - Tool/resource handlers no longer mutate or rely on private domain/infrastructure state.
  - Boundary matrix from `ARCHITECTURE.md` is satisfied with tests.
  - Regression suite remains green (`pytest` all tests pass).

### 2026-05-21 — P3 architecture enforcement checks and docs hygiene
- **Owner:** project governance
- **Inputs:** `ARCHITECTURE.md`, `AGENTS.md`, `ROADMAP.md`, `CHANGELOG.md`, `pyproject.toml`
- **Scope:** codify boundary checks in release process and documentation.
- **Acceptance:**
  - ROADMAP contains measurable gates for each retry-ready task.
  - CHANGELOG has a chronological entry for every behavior-affecting or governance-affecting change.
  - `test -f AGENTS.md && test -f ARCHITECTURE.md && test -f CHANGELOG.md && test -f ROADMAP.md` is enforced as pre-task check.

## Long-term

### 2026-06-01 — Evaluation closure and benchmark baselines
- **Owner:** platform + QA
- **Inputs:** benchmark outputs in `tests/benchmarks/results/`, test logs under `.benchmarks/`
- **Scope:** finish benchmark comparison matrix and archive baseline performance against prompt-only baseline.
- **Acceptance:**
  - One complete matrix run per benchmark target with artifacts committed to repo logs/results path.
  - Regression acceptance threshold is documented and applied to future changes affecting routing/competition behavior.
