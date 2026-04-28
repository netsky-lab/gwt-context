# Changelog

## 2026-04-28

- Added MCP memory management tools for namespace profiling, runtime reset,
  JSONL export/import, namespace tagging on stored records, and structured
  read-model restoration from persisted memory after MCP startup.
- Added broadcast-bus arbitration decision reason codes, serialized bus
  summaries, proposal grouping, and richer `broadcast_bus` inspect output.
- Added runtime configuration for broadcast-bus budgets and optional
  OpenAI-compatible external subscribers in the MCP composition root.
- Added integration regressions proving recurrent linked-memory activation
  reaches workspace and accepted subscriber queries affect later attention
  passes.
- Added Codex MCP bootstrap and health scripts, npm aliases, and docs for
  dry-run registration, namespace inspection, and temp-dir smoke checks.
- Split Codex MCP memory into project/global namespace guidance, added
  `scripts/clear_codex_memory.py` for safe namespace cleanup, and reconfigured
  the local Codex MCP entries to use project-specific and global data dirs.
- Added real stdio MCP client smoke coverage, Codex MCP setup docs, an
  infrastructure OpenAI-compatible external subscriber adapter, local release
  gate and Qwen sanity scripts, CI runtime smoke/boundary steps, and richer
  trace HTML grouping for proposal groups, inhibited proposals, and workspace
  changes.
- Bumped package metadata to `0.2.1`, added release note files for `v0.2.0`
  and `v0.2.1`, documented demo scenarios, added deterministic real MCP usage
  and external subscriber proof-of-concept examples, and improved benchmark
  trace HTML with phase timelines, bus action counts, policy skip counts, and
  subscriber status badges.
- Added the `v0.2.0` release threshold matrix, local quickstart, external
  subscriber adapter documentation, and `ExternalReasoningSubscriber` for
  port-safe LLM/NLI proposal generators.
- Added bus subscriber execution reports with timeout/error statuses, explicit
  `BusAdmissionPolicy` decisions, structured record contradiction detection,
  `gwt_bus_inspect`, bus on/off matrix helpers, trace bus summaries, and the
  concrete GWT runtime contract documentation.

## 2026-04-27

- Moved post-broadcast subscriber fan-out into `SelectionBroadcastCycle`, made
  accepted `resolve_answer`/flag/follow-up proposals actionable in
  `gwt_attend`, added proposal inhibition, recurrent linked-memory activation,
  and `GWT_MIN_ACTIVATION` workspace ignition gating.
- Added an application-level post-broadcast subscriber bus with structured resolve, semantic recall, relation continuation, contradiction checking, plan critique proposals, arbitration, and attention trace integration.
- Bumped package metadata to `0.2.0`, added CI, release-readiness documentation, MCP tool contract snapshots, and an 11-task bounded Qwen attend evaluation summary.
- Added deterministic hash embeddings for offline startup, a `gwt_context.smoke` readiness workflow, config env parity tests, MCP input validation, natural-language relation graph edges, and bounded Qwen smoke verification.
- Added generic runtime record extraction, first-class collection evidence, relation graph resolution, planner modes, runtime indexing, agent-facing MCP resolve/query/trace tools, and real workload eval coverage.
- Removed generated benchmark artifacts from git history and replaced real benchmark endpoint examples with placeholders.
- Added structured employee collection evidence for production attend, exact count/filter/aggregate/synthesis/top-k resolution, release gates, and refreshed Qwen deploy-candidate reports.
- Added parameterized multi-pass `gwt_attend`, structured generic planner queries, attend failure analysis, and a release baseline documenting deploy readiness.
- Added benchmark comparison tables with evidence metrics and refreshed one-pass/two-pass Qwen attend reports for RULER and LongBench Pro.
- Added benchmark `--gwt-mode attend`, `gwt://attention/last`, and an npm benchmark smoke script.
- Refreshed Qwen tools/attend reports after `admit=true` and prompt/schema changes, including a synthesis smoke run.
- Expanded the generic planner with relation-aware query planning for production `gwt_attend`.
- Added MCP `gwt_attend` for one-call goal-directed attention and added `admit` support to `gwt_query`.
- Added a production generic evidence planner, evidence precision/recall benchmark metrics, deterministic benchmark regression smoke, and LongBench synthesis tasks.
- Added an attention-controller architecture note documenting the controlled/hybrid design rationale and regression gates.
- Added reusable `AttentionController` in the application layer for goal-directed evidence planning, query admission, and broadcast through ports.
- Moved benchmark-specific controlled evidence logic into a resolver registry, including top-k employee aggregation support.
- Extended benchmark analysis with failure buckets, token/latency ratios, workspace occupancy metrics, and an updated four-mode Qwen report.
- Added a local MCP demo scenario using deterministic embeddings and committed npm lockfile metadata for reproducible `npm test` setup.
- Added hybrid GWT benchmark mode that uses deterministic GWT routing with model-only final synthesis.
- Added benchmark trace HTML rendering and a four-mode Qwen matrix report covering prompt-only baseline, model-controlled tools, deterministic controlled routing, and hybrid routing.
- Added MCP smoke coverage over registered tools/resources using public MCP handlers and real application wiring.
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
