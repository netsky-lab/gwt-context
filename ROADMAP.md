# Roadmap

## Current State

- Baseline runtime and tests: Python 3.11+, MCP server (`python -m gwt_context`), local smoke (`python -m gwt_context.smoke`), and `pytest` baseline of 161 passing tests.
- Architecture baseline is established in `ARCHITECTURE.md`; active work is P5/P6 boundary migration.
- Benchmark entrypoints are present and runnable:
  - `python -m tests.benchmarks.ruler_multi_hop`
  - `python -m tests.benchmarks.longbench_pro`
- Local and benchmark smoke can use `GWT_EMBEDDING_PROVIDER=hash` to avoid
  embedding model downloads during readiness checks.
- CI covers `pytest`, `ruff`, `mypy`, `npm test`, and package build.
- MCP response contracts are documented in `docs/mcp-tool-contracts.md` and
  guarded by snapshot-style unit tests.
- `SelectionBroadcastCycle` includes a post-broadcast subscriber bus so
  broadcast is an event consumed by independent proposal-generating processors,
  not only text returned to one downstream model call. `gwt_attend` applies
  accepted proposal kinds and records inhibited repeats in the trace.
- Broadcast subscribers now produce execution reports with timeout/error
  statuses, and bus admission decisions are governed by an explicit
  `BusAdmissionPolicy`.
- Workspace admission has an ignition threshold through `GWT_MIN_ACTIVATION`.
- Conscious workspace items reactivate explicit linked memories into the
  preconscious buffer for recurrent link-following cycles.
- `docs/gwt-runtime-contracts.md` records the concrete preconscious,
  conscious, bus, and admission contracts.
- `ExternalReasoningSubscriber` defines the port-safe adapter path for future
  LLM/NLI subscriber loops without coupling application code to provider SDKs.
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

### 2026-04-30 — P8 attention-controller evaluation loop
- **Owner:** application architecture + benchmark platform
- **Inputs:** `src/gwt_context/application/attention.py`, `tests/benchmarks/*`, benchmark reports.
- **Scope:** make successful controlled/hybrid selection reusable outside benchmark harness while keeping task-specific resolvers pluggable.
- **Acceptance:**
  - Attention controller depends only on application ports.
  - Benchmark controlled/hybrid modes use resolver adapters instead of embedding controller flow in the harness.
  - Analyzer reports failure buckets and token/latency/workspace metrics for future regressions.

### 2026-05-02 — P9 runtime attention MCP surface
- **Owner:** MCP boundary + application architecture
- **Inputs:** `src/gwt_context/mcp/tools.py`, `src/gwt_context/application/attention.py`, benchmark smoke.
- **Scope:** expose explicit attention control as runtime MCP API and measure evidence selection quality.
- **Acceptance:**
  - `gwt_attend` runs through public application ports and does not import benchmark resolvers.
  - `gwt_query(admit=true)` is covered by boundary and integration tests.
  - Deterministic benchmark smoke runs without external model/API calls.
  - `--gwt-mode attend` is available for model-backed production planner evaluation.
  - Runtime planner modes are exposed as `auto`, `semantic`, `structured`,
    `graph`, and `hybrid`.
  - Agent-facing exact-resolution tools cover direct resolve, collection query,
    and trace explanation.
  - Local readiness smoke covers server creation, store, graph resolve, attend,
    trace explanation, and stats without external embedding downloads.
  - Attention traces include post-broadcast subscriber proposals and accepted
    downstream actions.
  - `BENCHMARK_ATTEND_BROADCAST_BUS=0/1` can isolate bus contribution in attend
    benchmark runs.
  - `tests.benchmarks.bus_matrix` builds/runs/summarizes bounded bus on/off
    evaluation commands.
  - Multi-pass attention remains opt-in through `gwt_attend(passes=...)` and
    `BENCHMARK_ATTEND_PASSES` until benchmark evidence justifies a new default.
  - Structured collection tasks have explicit release gates in benchmark
    reports for count, filter, aggregate, synthesis, and top-k task families.
  - `docs/release-thresholds.md` records the blocking gates for release tags.

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
  - CI remains green across Python checks, npm verification, and package build.

## Long-term

### 2026-06-01 — Evaluation closure and benchmark baselines
- **Owner:** platform + QA
- **Inputs:** benchmark outputs in `tests/benchmarks/results/`, test logs under `.benchmarks/`
- **Scope:** finish benchmark comparison matrix and archive baseline performance against prompt-only baseline.
- **Acceptance:**
  - One complete matrix run per benchmark target with artifacts committed to repo logs/results path.
  - Regression acceptance threshold is documented and applied to future changes affecting routing/competition behavior.
