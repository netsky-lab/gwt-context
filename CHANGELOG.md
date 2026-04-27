# Changelog

## 2026-04-27

- Added controlled GWT benchmark mode with deterministic router/specialists for RULER chains and LongBench count/filter/aggregate tasks.
- Fixed RULER generated question wording so hop count matches expected answers.
- Added a controlled Qwen benchmark matrix showing GWT controller performance against prompt-only baseline.
- Added benchmark trace artifacts, result analysis helpers, and research-backed design rationale for GWT architecture decisions.
- Added a Qwen benchmark matrix report and hardened benchmark tool execution so malformed model tool arguments are recorded as trace errors instead of aborting tasks.
- Made sentence-transformer lazy initialization thread-safe for concurrent benchmark runs.

## 2026-04-26

- Added a `research/` cache with current 2025-2026 GWT/GNWT papers, source metadata, and design implications for the project.
- Removed direct MCP resource coupling to cycle workspace/buffer/goal internals by routing workspace, goals, and stats resources through `CyclePort` read-model APIs.
- Added a current-workspace broadcast read method to the cycle port and implementation for resource use without running a broadcast cycle.
- Updated baseline documentation to avoid stale test-count drift and record the current `pytest` baseline.
- Updated benchmark defaults for the Qwen RunPod endpoint and made `BENCHMARK_CONCURRENCY` execute independent benchmark tasks in parallel.
- Normalized sentence-transformer outputs to Python float lists so benchmark ingestion/storage does not receive numpy arrays.

## 2026-04-19

- Synced benchmark CLI defaults with config precedence for `BENCHMARK_RESULTS_DIR` in
  `tests/benchmarks/ruler_multi_hop.py` and `tests/benchmarks/longbench_pro.py`.
- Added regression tests covering env-backed benchmark `results_dir` defaults and
  explicit CLI `results_dir` propagation in `tests/unit/test_benchmark_config.py`
  and `tests/unit/test_benchmark_harness.py`.

## 2026-04-19

- Stabilized benchmark harness/runtime configuration in `tests/benchmarks/config.py` with explicit CLI/env validation (`BENCHMARK_API_BASE`, `BENCHMARK_API_PATH`, `BENCHMARK_MODEL`, timeout, headers, retries, concurrency, results dir).
- Updated `tests/benchmarks/harness.py` to construct OpenAI clients from deterministic config, compute stable run metadata and write JSON results atomically with deterministic filenames into a single canonical results directory.
- Extended benchmark CLI entrypoints (`tests/benchmarks/ruler_multi_hop.py`, `tests/benchmarks/longbench_pro.py`) with `--api-path`, `--timeout`, `--api-headers`, `--max-retries`, and `--concurrency` plus documented run-dir behavior.
- Added reproducibility documentation (`tests/benchmarks/README.md`) and refreshed `.env.example`/root `README.md` benchmark setup guidance.
- Added unit coverage for benchmark config parsing and harness persistence (`tests/unit/test_benchmark_config.py`, `tests/unit/test_benchmark_harness.py`).


## 2026-04-19

- Re-aligned onboarding docs to a single source of truth (`AGENTS.md`, `ARCHITECTURE.md`, `ROADMAP.md`) with explicit architecture-boundary checks captured in task planning.
- Updated baseline docs to current test count and command expectations (`78` passing tests; `npm test` documented as task verification entrypoint).
- Re-added/retained explicit onboarding checklist requirements for forbidden imports, coupling checks, and rollback conditions.

## 2026-04-19

- Added repository-level shared onboarding docs: `AGENTS.md`, `ROADMAP.md`, and `ARCHITECTURE.md`.
- Defined the documentation bootstrap decision and rationale to establish a single source of truth for task onboarding and architecture-boundary enforcement.
- Added task-planning requirements to record architecture inbounds/outbounds, forbidden imports/coupling, and documentation/changelog update expectations before implementation changes.
- Updated this changelog with a dated entry preserving reverse-chronological order and decision traceability.
- Refactored `SelectionBroadcastCycle`, `IngestionPipeline`, and `GoalManager` to accept only interface ports from `interfaces/ports.py`.
- Added new `GoalManagerPort` protocol and kept vector/store/embedding collaborators as ports in application constructors.
- Added unit coverage for port-based construction and server composition wiring (`tests/unit/test_application_ports.py`).

## 2026-04-19

- Added `src/gwt_context/interfaces/ports.py` to define target application/MCP contracts.
- Synchronized `ARCHITECTURE.md` with current repository boundaries, entrypoint ownership, import directions, and explicit P5/P6 migration blocks.
- Documented and created baseline `AGENTS.md` and `ROADMAP.md` to unblock architecture/task ordering requirements.
- Added `SelectionBroadcastCycle` MCP-facing methods (`run_competition_dry`, `enqueue_for_competition`, `set_goal`, `evict_workspace_item`, `link_items`, `inspect`) so MCP boundary contracts are explicit in code.
- Switched `mcp.tools`/`mcp.resources` to port-oriented typing and added in-source quality fixes for ruff/mypy issues in `src/`.
- Updated quality config to keep gate scope focused on source package (`exclude = ["tests"]`) in `pyproject.toml`.

## 2026-04-13

- Fix in-memory link consistency after `gwt_link`: newly created bidirectional links now update already-loaded buffer/workspace `MemoryItem` instances in the same session so the next competition round sees the new graph.
- Added regressions for live object link sync and multi-hop competition after linking.

## 2026-04-19

- Added target clean architecture baseline in ARCHITECTURE.md.
- Defined explicit layer dependency rules, composition-root responsibilities, import matrix, and ADR-1..ADR-4.
- Added explicit forbidden leak list and a migration path for P5 (ports-first application refactor) and P6 (MCP boundary cleanup).

## 2026-04-19

- Refined `ARCHITECTURE.md` with interface-layer target map, allowed/forbidden import matrix, and operation flow diagrams (memory ingest/link/inspect).
- Added explicit migration enforcement checks for P5/P6 and concrete review gate checklist.
