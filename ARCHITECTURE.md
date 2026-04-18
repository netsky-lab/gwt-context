# Target Architecture and Boundaries

## 1) Purpose

This document defines the **target** clean architecture for `gwt-context` in a form that can be enforced during P5 (ports-first application refactor) and P6 (MCP boundary cleanup).

The current implementation works end-to-end, but it still binds across layers in two key places:

- `server.py` constructs concrete infrastructure classes directly.
- MCP handlers and resources reach into application internals (`cycle`, `goal_manager`, `buffer`, `workspace`, etc.).

The target below is not a rewrite of code; it is a contract for the next refactor.

## 2) Current module map

```text
src/gwt_context/
├── domain/
│   ├── models.py
│   ├── workspace.py
│   ├── competition.py
│   ├── specialists.py
│   └── broadcast.py
├── application/
│   ├── cycle.py
│   ├── ingestion.py
│   └── goal_manager.py
├── infrastructure/
│   ├── config.py
│   ├── embeddings.py
│   ├── storage.py
│   └── vector_index.py
├── mcp/
│   ├── tools.py
│   ├── resources.py
│   └── prompts.py
└── server.py
```

## 3) Allowed dependency directions

- `MCP -> Application` (or interfaces) is allowed.
- `Application -> Domain` is allowed.
- `Infrastructure -> Domain` is allowed.
- `Infrastructure -> Application` is forbidden.
- `Application -> Infrastructure` (concrete classes and adapters) is forbidden.
- `MCP -> Infrastructure` is forbidden.
- `Domain -> *` is forbidden.

## 4) Service interfaces (ports) and responsibility boundaries

The following ports describe *target* dependencies; implementations stay in Infrastructure unless noted.

| Port | Contract (target) | Owner | Default interface target | Consumer |
| --- | --- | --- | --- | --- |
| `MemoryRepositoryPort` | read/write/query memory items, goal CRUD, broadcast persistence, link updates | `infrastructure/storage.py` | `src/gwt_context/application` consumes methods like `get_item`, `get_all_items`, `get_items_by_state`, `save_item`, `update_state`, `add_link`, goal APIs | `application.cycle`, `application.ingestion`, `application.goal_manager`, `mcp.resources` |
| `VectorSearchPort` | vector add/query/persist semantics | `infrastructure/vector_index.py` | `src/gwt_context/application` consumes `add`, `query`, `save`, `count`, `remove`, `load` semantics | `application.ingestion`, `application.cycle`, `server` (init) |
| `EmbeddingPort` | deterministic embedding + batch embedding | `infrastructure/embeddings.py` | `src/gwt_context/application` consumes `embed`, `embed_batch`, `dim` | `application.ingestion`, `application.goal_manager`, `server` |
| `CyclePort` (application service) | orchestration operations exposed to MCP | `application/cycle.py` | `mcp.tools` consumes `run`, `run_competition_dry`, `enqueue_for_competition`, `set_goal`, `inspect`, `evict_workspace_item`, `link_items` | `mcp.tools`, `mcp.resources` |
| `IngestionPort` | ingestion command API | `application/ingestion.py` | `mcp.tools` consumes `ingest`, `query_similar` | `mcp.tools` |

All MCP-facing operations should use explicit application service ports; MCP modules must not call domain or infrastructure internals directly.

## 5) Composition root responsibilities (`server.py`)

`server.py` is the only place where concrete implementations are instantiated and wired.

Target responsibilities:

- read config from environment
- build concrete infra dependencies
- build domain services/factories
- adapt concrete infra to the application ports
- assemble application services
- register MCP tools/resources against the assembled application services
- restore startup state via application service or orchestrated state-restorer utility

Target anti-responsibilities for `server.py`:

- no domain scoring/ranking policy
- no lifecycle orchestration logic
- no direct MCP implementation logic
- no direct mutation of domain entities outside construction/registration

## 6) Module/import matrix (current vs target)

| Module | Current imports (observed) | Target imports | Status |
| --- | --- | --- | --- |
| `server.py` | concrete infra, domain, application, mcp | same + composition-only; no logic migration here | ✅ keep composition only |
| `application/cycle.py` | imports `domain` + concrete `infrastructure.storage/vector_index` | replace concrete infra imports with repository/vector ports | ⚠ P5 |
| `application/ingestion.py` | imports `domain` + concrete infra | replace concrete infra with repository/vector/embedding ports | ⚠ P5 |
| `application/goal_manager.py` | imports `domain` + concrete infra | replace `SQLiteMemoryStore` and `EmbeddingProvider` with ports/interfaces | ⚠ P5 |
| `mcp/tools.py` | imports `SelectionBroadcastCycle`, `IngestionPipeline`; reads fields via method calls only now but still tied to concrete cycle internals conceptually | keep app services via ports, no infra/domain internals | ✅ boundary-safe for calls, harden with interface typing |
| `mcp/resources.py` | imports `SelectionBroadcastCycle` and `SQLiteMemoryStore` | replace with `CyclePort` and domain read DTOs / memory repo service (or read adapter) | ⚠ P6 |
| `mcp/prompts.py` | self-contained prompt strings | no dependency change | ✅ |

## 7) Concerns that must not leak across layers

### Forbidden across boundaries

- MCP modules may not import concrete infra classes (`SentenceTransformerEmbedder`, `SQLiteMemoryStore`, `VectorIndex`).
- MCP modules may not traverse into application internals/private attributes.
- Application modules may not instantiate MCP artifacts.
- Domain must not import storage, vector, embedding, MCP, or server concerns.

### Required layering outcomes

- Domain objects remain pure data + behavior for invariants and scoring helpers.
- Application owns orchestration and enforces policies through domain services.
- Infrastructure provides concrete technical mechanisms behind ports.
- MCP defines contract and transport surface only.

## 8) ADR-1: Port-first dependency strategy

- Date: 2026-04-19
- Context: Concrete infra imports currently appear in `application/*` and should be removed before future refactors can progress safely.
- Decision: Introduce `MemoryRepositoryPort`, `VectorSearchPort`, `EmbeddingPort`, and `CyclePort` as the only cross-layer access points from application to infrastructure and MCP.
- Rationale: Decouples external APIs (SQLite/transformers/index choice) from orchestration and enables testable unit boundaries.
- Consequences: Refactoring requires explicit constructor signatures and thin adapters in the composition root.

## 9) ADR-2: Composition root ownership in `server.py`

- Date: 2026-04-19
- Context: Wiring exists but with direct, broad coupling and state restoration concerns mixed into startup.
- Decision: `server.py` remains the only place that creates concrete instances; all non-trivial orchestration uses application services built from ports.
- Rationale: Keeps startup deterministic, avoids import cycles, and makes integration testing easier via injected fakes.
- Consequences: startup path becomes explicit and testable; deeper orchestration logic migrates out into app services.

## 10) ADR-3: Persistence/search/vector boundary separation

- Date: 2026-04-19
- Context: `storage.py`, `vector_index.py`, and `embeddings.py` currently appear in application import chains.
- Decision: Infrastructure is sole owner of persistence/search/embedding implementation; application interacts only through ports.
- Rationale: Enables swap from SQLite+hnsw-style numpy index to other stores without touching application logic.
- Consequences: adapter classes may be required for protocol mismatches; startup remains in `server.py`.

## 11) ADR-4: MCP boundary should transport app-level intents, not domain state

- Date: 2026-04-19
- Context: MCP resources/tools currently depend on `SelectionBroadcastCycle` internals and concrete repository classes, leaking implementation details.
- Decision: MCP modules consume application ports and return serialized DTO-like maps for UI/output contracts.
- Rationale: Preserves transport stability and prevents state-shape breakage from leaking into protocol handlers.
- Consequences: `mcp/resources.py` and `mcp/tools.py` become thin facades; richer output is shaped by application services.

## 12) Migration path for P5/P6

### P5 (application depends on ports)
1. Add protocol/ABC interfaces for each `*Port` in `application/ports.py`.
2. Refactor constructors in `cycle.py`, `ingestion.py`, and `goal_manager.py` to accept ports.
3. Add thin infrastructure adapters in `infrastructure/` where needed.
4. Update `server.py` to instantiate adapters and pass them in.
5. Add/adjust unit tests for constructor signatures and adapter behavior.

### P6 (MCP boundary cleanup)
1. Add explicit application service interfaces for MCP-visible behavior (`CyclePort`, `IngestionPort`).
2. Replace direct `SQLiteMemoryStore` usage in `mcp/resources.py` with service calls.
3. Replace any direct field access to cycle internals with dedicated application methods.
4. Keep MCP handlers thin and declarative.
5. Verify with boundary tests that tools/resources only call declared application services.
