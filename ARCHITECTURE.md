# Architecture

## Purpose

`gwt-context` is a Python MCP server that maintains bounded working memory for LLM interactions using a selection-broadcast cycle. The implementation is organized in explicit layers: domain, application, infrastructure, MCP interface, and a composition root.

## Package Layout

- `src/gwt_context/domain/`
  - `models.py`: `MemoryItem`, `Goal`, `BroadcastRecord`, enums.
  - `workspace.py`: `GlobalWorkspace`, `WorkspaceSlot`.
  - `specialists.py`: scoring specialists used by arbitration.
  - `competition.py`: `CompetitionEngine` and result contracts.
  - `broadcast.py`: `BroadcastAssembler`.
- `src/gwt_context/application/`
  - `broadcast_bus.py`: post-broadcast subscriber bus, proposals, and arbitration.
  - `attention.py`: reusable attention controller for goal setting, evidence planning, query admission, and broadcast.
  - `structured.py`: runtime record extraction, exact collection evidence, and relation graph resolution.
  - `ingestion.py`: `IngestionPipeline` (content -> embedding -> persistence/index).
  - `goal_manager.py`: goal activation/modulation state.
  - `cycle.py`: `PreconsciousBuffer`, `SelectionBroadcastCycle` orchestration.
- `src/gwt_context/infrastructure/`
  - `config.py`: `GWTConfig` and env-backed runtime config.
  - `storage.py`: `SQLiteMemoryStore` persistence.
  - `vector_index.py`: numpy-based cosine similarity index.
  - `embeddings.py`: `EmbeddingProvider` + `SentenceTransformerEmbedder`.
- `src/gwt_context/interfaces/`
  - `ports.py`: boundary protocols (`CyclePort`, `IngestionPort`, `MemoryRepositoryPort`, etc.).
- `src/gwt_context/mcp/`
  - `tools.py`: MCP tool surface.
  - `resources.py`: MCP resources for read-only state.
  - `prompts.py`: prompt text.
- `src/gwt_context/server.py`: composition root and startup.
- `src/gwt_context/__main__.py`: `python -m gwt_context` bootstrap.

## Inbounds, Outbounds, and Boundaries

### Onboarding canonical checks

- Before any change, read `AGENTS.md`, `ROADMAP.md`, and this file before touching implementation.
- Boundaries for review:
  - No application module imports concrete infrastructure internals through direct implementation imports.
  - MCP modules (`tools.py`, `resources.py`, `prompts.py`) consume only public contracts and public domain/application state models.
  - `server.py` remains the only composition root that wires concrete infrastructure types.

- Inbound to the service: MCP clients calling tools/resources (`gwt_store`, `gwt_broadcast`, `gwt_query`, `gwt_set_goal`, etc.).
- Outbound dependencies:
  - `server.py` wires concrete implementations from `infrastructure` into domain and application.
  - `mcp/*` depends on `cycle`/`ingestion` contracts and domain models exposed via application ports.
  - `application/*` depends on contracts from `interfaces/ports.py`.
  - `domain/*` stays free of I/O and external integrations.

## Runtime Control Flow (Current, Implemented)

### 1) Ingest path

- MCP tool `gwt_store` → `IngestionPipeline.ingest`.
- Build `MemoryItem` + compute embedding.
- Write item + goal linkage to `SQLiteMemoryStore`.
- Add vector in `VectorIndex` and persist index.

### 2) Broadcast cycle path

| Port | Intent | Owner | Current implementation |
| --- | --- | --- | --- |
| `EmbeddingPort` | embed text + dimensions | `infrastructure/embeddings.py` | Used by `GoalManager`/`IngestionPipeline` via interface contracts. |
| `GoalManagerPort` | goal activation/selection API | `application/goal_manager.py` | Used by `SelectionBroadcastCycle` via interface contracts. |
| `VectorSearchPort` | add/query/save/remove vector state | `infrastructure/vector_index.py` | Used by `IngestionPipeline`/`SelectionBroadcastCycle` via interface contracts. |
| `MemoryRepositoryPort` | persistence for memory/goals/broadcasts + links | `infrastructure/storage.py` | Used by `GoalManager`/`IngestionPipeline`/`SelectionBroadcastCycle` via interface contracts. |
| `IngestionPort` | `ingest`, `query_similar` | `application/ingestion.py` | Exposed to MCP tools. |
| `CyclePort` | `run`, `run_competition_dry`, `enqueue_for_competition`, `set_goal`, `evict_workspace_item`, `link_items`, `inspect` | `application/cycle.py` | Implemented and called by MCP tools. |

- MCP tool `gwt_broadcast` → `SelectionBroadcastCycle.run`.
- **Candidate assembly:** from `PreconsciousBuffer.top()` + optional goal-driven vector retrieval in `VectorIndex`.
- **Score:** `CompetitionEngine` runs all specialists and applies goal modulation.
- **Compete:** winners are admitted to `GlobalWorkspace`; evicted items return to preconscious.
- **Format:** `BroadcastAssembler.assemble` produces a broadcast payload (`BroadcastRecord`) and writes it to storage.

### 2a) Explicit attention-controller path

- `AttentionController` lives in `application/attention.py` and depends only on `CyclePort` and `IngestionPort`.
- Task-specific planners implement the `EvidenceResolver` protocol and return an `EvidencePlan`.
- `GenericEvidenceResolver` supports semantic, structured collection, relation graph, hybrid, and auto planning without importing benchmark adapters.
- Runtime collection/relation extraction lives in `application/structured.py` and has no MCP or infrastructure dependency.
- The controller sets the active goal, runs resolver-selected queries, admits query matches into competition, then executes one broadcast cycle.
- After each broadcast, `BroadcastBus` fans out the globally available
  broadcast to independent subscribers. Subscribers return proposals such as
  exact resolution, semantic recall, relation continuation, contradiction
  flags, or follow-up requests.
- Broadcast subscribers do not mutate workspace directly. The bus arbitrates
  proposals and the controller applies accepted side effects through public
  application ports, such as `IngestionPort.query_similar` plus
  `CyclePort.enqueue_for_competition`.
- Benchmark resolvers are adapters under `tests/benchmarks/controlled_rules.py`; production MCP handlers do not import benchmark code.

### 3) Explicit key data path

`storage load -> scoring -> competition -> workspace -> broadcast`

- Storage-backed records provide candidate set material.
- Specialists score candidates.
- `CompetitionEngine` arbitrates winners.
- Winners update `GlobalWorkspace`.
- `BroadcastAssembler` formats workspace content for downstream use.

### 4) Read and inspection path

- `server.py`: imports concrete infra and registers MCP against concrete runtime services.
- `application/*`: depends on interface ports for external collaborators.
- `mcp/tools.py`: typed against `CyclePort`/`IngestionPort`.
- `mcp/resources.py`: uses cycle-derived in-memory views and repository reads for resource payloads.

- `gwt_query` executes semantic lookup via `IngestionPipeline.query_similar` and returns candidates.
- `gwt_query(admit=true)` enqueues returned candidates for the next competition round.
- `gwt_attend` executes the explicit attention-controller path through public application ports.
- `gwt_resolve`, `gwt_collection_query`, and `gwt_trace_explain` expose agent-facing resolution and trace inspection without reaching into private runtime internals.
- `gwt://attention/last` exposes the most recent attention trace through an in-memory read model.
- `gwt_inspect` and MCP resources expose `workspace`, `buffer`, `goals`, and `stats` through cycle/read model paths.

## Persistence and I/O Model

### Memory and goals

- Persistent store: `memory.db` (SQLite) under `GWT_DATA_DIR`.
- Tables are created and managed by `SQLiteMemoryStore`:
  - `memory_items`, `goals`, `links`, `broadcasts`.

### Vector index

- Numpy files under `GWT_DATA_DIR/` from `GWT_VECTOR_INDEX_PATH`:
  - metadata JSON (`.json`) and vectors (`.npy`).
- Rebuild behavior: on startup, if vector index is empty but DB has embedded items, `server._restore_state` repopulates and saves vectors.

### Model artifacts

- Embeddings generated by `SentenceTransformerEmbedder` from `GWT_EMBEDDING_MODEL` and dimensions in `GWT_EMBEDDING_DIM`.

## Config and Environment Inputs

From `src/gwt_context/infrastructure/config.py` and `.env` loading:
- `GWT_WORKSPACE_CAPACITY`
- `GWT_BUFFER_SIZE`
- `GWT_GOAL_MODULATION`
- `GWT_EMBEDDING_PROVIDER`
- `GWT_EMBEDDING_MODEL`
- `GWT_EMBEDDING_DIM`
- `GWT_DATA_DIR`
- `GWT_MAX_BROADCAST_TOKENS`
- `GWT_MAX_VECTOR_ELEMENTS`
- `GWT_DB_PATH` (override path if set)
- `GWT_VECTOR_INDEX_PATH` (override path if set)

Defaults are applied when vars are absent via `GWTConfig.from_env()`.
`GWT_EMBEDDING_PROVIDER=hash` selects deterministic local embeddings for
offline readiness checks and benchmark smoke runs that should not download a
sentence-transformer model.

## Tested Boundaries and Entry Points

- Entrypoint:
  - `python -m gwt_context`
  - `gwt-context` script from `pyproject.toml`.
- Composition root:
  - `server.create_server()` and `server.main()` are the only process bootstrap points.
- Verified baseline test surface:
  - `pytest` against `tests/unit` and `tests/integration`.
