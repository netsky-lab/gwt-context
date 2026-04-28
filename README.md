# gwt-context

Global Workspace Theory implementation for LLM context management. MCP server with selection-broadcast cycle, specialist competition, and multi-hop reasoning.

## What it does

LLMs lose information in long contexts — multi-hop reasoning degrades (Sequential-NIAH best: 63.15%), information aggregation suffers (LongBench Pro T6: 57.72%). Existing solutions (MemGPT, Sculptor, A-MEM, etc.) don't implement the core GWT mechanism.

**gwt-context** implements a real Global Workspace Theory selection-broadcast cycle as an MCP server. Specialist processors compete to surface the most relevant information into a capacity-limited workspace. The workspace content is broadcast globally to the LLM on every cycle.

### GWT markers implemented

| Marker | Implementation |
|--------|---------------|
| Global availability | Workspace broadcast — all items visible simultaneously |
| Functional concurrency | 6 specialists score independently |
| Coordinated selection | CompetitionEngine — single arbitration point |
| Capacity limitation | Workspace capacity = 7 (Miller's 7±2) |
| Persistence with controlled update | Items persist until displaced by competition |
| Goal-modulated arbitration | ×1.3 multiplicative boost by goal relevance |

## Install

```bash
pip install gwt-context
```

**Requirements:** Python 3.11+, sentence-transformers (all-MiniLM-L6-v2, downloaded on first run).

## Usage

### With Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "gwt-context": {
      "command": "python",
      "args": ["-m", "gwt_context"]
    }
  }
}
```

### With any MCP client

```bash
python -m gwt_context
```

### Local readiness smoke

Use hash embeddings when you want a fully local startup check without
downloading a sentence-transformer model:

```bash
GWT_EMBEDDING_PROVIDER=hash GWT_EMBEDDING_MODEL=hash python -m gwt_context.smoke
```

The same command is available after installation as `gwt-context-smoke`.

## MCP Tools

| Tool | Description |
|------|------------|
| `gwt_store` | Store content in long-term memory (embed + index + buffer) |
| `gwt_set_goal` | Set active goal — biases competition toward goal-relevant items |
| `gwt_broadcast` | Run selection-broadcast cycle — returns workspace content |
| `gwt_compete` | Competition round without broadcast (dry-run) |
| `gwt_query` | Semantic search over long-term memory, optionally admitted to competition |
| `gwt_attend` | One-call goal-directed attention pass with semantic, structured, graph, hybrid, or auto planning |
| `gwt_resolve` | Resolve a question against runtime structured memory without broadcasting |
| `gwt_collection_query` | Run exact count/filter/top-k/average/compare operations over runtime structured memory |
| `gwt_trace_explain` | Explain the most recent explicit attention trace |
| `gwt_evict` | Manual eviction from workspace |
| `gwt_link` | Bidirectional link between items (enables multi-hop chains) |
| `gwt_inspect` | Observe workspace, buffer, goals, stats |

## How it works

```
 ┌─────────────────────────────────────────────────┐
 │                  Long-Term Memory               │
 │            (SQLite + Vector Index)               │
 └──────────────────┬──────────────────────────────┘
                    │ candidates
                    ▼
 ┌──────────────────────────────────────────────────┐
 │              Specialist Processors               │
 │                                                  │
 │  Relevance (0.35)    Recency (0.20)              │
 │  Novelty (0.15)      Frequency (0.10)            │
 │  Structural Linkage (0.10)  Goal Linkage (0.10)  │
 └──────────────────┬───────────────────────────────┘
                    │ scored candidates
                    ▼
 ┌──────────────────────────────────────────────────┐
 │            Competition Engine                    │
 │     weighted scores + goal modulation (×1.3)     │
 │     top-N admitted, losers evicted               │
 └──────────────────┬───────────────────────────────┘
                    │ winners
                    ▼
 ┌──────────────────────────────────────────────────┐
 │          Global Workspace (capacity=7)           │
 │                                                  │
 │    Broadcast → formatted text returned to LLM    │
 └──────────────────────────────────────────────────┘
```

### Multi-hop reasoning

Items can be linked bidirectionally via `gwt_link`. The **GoalLinkageSpecialist** weights each link by how relevant the linked item is to the current goal — multi-hop chains are boosted only when they lead toward the goal. The **StructuralLinkageSpecialist** preserves chains across minor goal shifts.

### Goal switching

When the goal changes, GoalLinkageSpecialist re-weights all links by relevance to the new goal. Items linked to now-irrelevant content lose their boost and get evicted, making room for goal-relevant items.

### Explicit attention control

`gwt_context.application.attention.AttentionController` provides a reusable path for deterministic selection: set the goal, resolve an evidence plan, query/admit matching memories, then broadcast. Production planning supports semantic lookup, exact structured collection evidence, relation-graph continuation, hybrid mode, and auto mode. The controller itself depends only on application ports.

`SelectionBroadcastCycle` publishes each workspace broadcast to a subscriber
bus. Structured resolve, semantic recall, relation continuation, contradiction
checking, and plan critique subscribers read the same broadcast and return
proposals. `gwt_attend` applies accepted proposals through public ports:
follow-up memory queries, deterministic answer resolution, contradiction flags,
and follow-up flags are recorded in the trace. Repeated proposals are inhibited
across broadcasts.

Conscious items also reactivate their `gwt_link` targets into the preconscious
buffer for the next cycle, so recurrent attention can follow explicit memory
links instead of only parsing names from rendered broadcast text.

The strict state/admission rules are documented in
[`docs/gwt-runtime-contracts.md`](docs/gwt-runtime-contracts.md).
Start from [`docs/quickstart.md`](docs/quickstart.md) for local usage and
[`docs/external-subscribers.md`](docs/external-subscribers.md) for LLM/NLI
subscriber adapters.

MCP clients can call `gwt_attend(question, keywords?, k?, planner?)` for this path without
manually sequencing `gwt_set_goal`, `gwt_query(admit=true)`, and `gwt_broadcast`.
They can also call `gwt_resolve` or `gwt_collection_query` when they need an exact runtime answer without a broadcast. The most recent attention trace is available at `gwt://attention/last` and summarized by `gwt_trace_explain`.
`gwt_bus_inspect` exposes the latest cycle-level bus result, including
subscriber statuses and accepted/inhibited proposal counts.

## Architecture

```
src/gwt_context/
├── domain/           # Pure domain, no I/O
│   ├── models.py     # MemoryItem, Goal, WorkspaceSlot, etc.
│   ├── workspace.py  # GlobalWorkspace (capacity-limited slots)
│   ├── specialists.py # 6 specialist scoring functions
│   ├── competition.py # CompetitionEngine (scoring + eviction)
│   └── broadcast.py  # BroadcastAssembler (workspace → text)
├── application/      # Orchestration
│   ├── broadcast_bus.py # Post-broadcast subscribers and proposal arbitration
│   ├── attention.py  # Explicit attention controller
│   ├── structured.py # Runtime collection and relation evidence
│   ├── cycle.py      # SelectionBroadcastCycle + PreconsciousBuffer
│   ├── ingestion.py  # Content → MemoryItem pipeline
│   └── goal_manager.py
├── infrastructure/   # Storage, embeddings
│   ├── storage.py    # SQLiteMemoryStore
│   ├── vector_index.py # Numpy cosine similarity index
│   ├── embeddings.py # SentenceTransformerEmbedder
│   └── config.py     # GWTConfig
├── mcp/              # MCP interface
│   ├── tools.py      # 12 tool definitions
│   ├── resources.py  # MCP resources
│   └── prompts.py    # System + multi-hop prompts
└── server.py         # FastMCP wiring + entry point
```

## Tests

```bash
pip install -e ".[dev]"
pytest tests/unit/ tests/integration/ -q
```
Tests cover domain logic, storage, vector index, MCP boundaries, and full selection-broadcast cycles.

## Benchmarks

Benchmark harness for evaluation against OpenAI-compatible APIs (Qwen, Llama, etc. via vLLM/TGI):

```bash
pip install -e ".[dev,bench]"
cp .env.example .env
```

```bash
python -m tests.benchmarks.ruler_multi_hop
```

```bash
python -m tests.benchmarks.longbench_pro
```

See [`tests/benchmarks/README.md`](tests/benchmarks/README.md) for the full variable matrix, command examples, and reproducible output behavior.
See [`docs/attention-controller.md`](docs/attention-controller.md) for the architecture note behind the controlled/hybrid design.
See [`docs/release-readiness.md`](docs/release-readiness.md) for current release gates and Qwen smoke status.
See [`docs/mcp-tool-contracts.md`](docs/mcp-tool-contracts.md) for stable MCP response shapes.

Each benchmark runs GWT mode (with tools) and baseline mode (all context in prompt) for comparison.
Results are saved as JSON in `BENCHMARK_RESULTS_DIR` (default `tests/benchmarks/results/`) using deterministic filenames:

- `{benchmark}_{model}_{timestamp}_{config_hash}.json`

Benchmark modes include prompt-only baseline, model-controlled `tools`,
production generic `attend`, deterministic `controlled`, and `hybrid` mode
where GWT selection is deterministic and the model only performs final
synthesis.

Analyze failures and runtime metrics with:

```bash
python -m tests.benchmarks.analyze_results tests/benchmarks/results
```

Render trace-heavy results as HTML with:

```bash
python -m tests.benchmarks.render_trace tests/benchmarks/results/<result>.json
```

Run a small local MCP-facing scenario without downloading embedding models:

```bash
python examples/mcp_demo.py
```

Run the deterministic benchmark smoke used by `npm test`:

```bash
npm run benchmark:smoke
```

Run a tiny model-backed Qwen/OpenAI-compatible smoke while keeping local GWT
embeddings deterministic:

```bash
GWT_EMBEDDING_PROVIDER=hash GWT_EMBEDDING_MODEL=hash \
python -m tests.benchmarks.ruler_multi_hop \
    --hops 2 --distractors 3 --tasks-per-config 1 --max-tasks 1 \
    --gwt-mode attend
```

### RunPod endpoint

The benchmark entrypoints load `.env` automatically if it exists. The repository now includes `.env.example` with the current RunPod-compatible defaults:

```dotenv
BENCHMARK_API_BASE=https://example-openai-compatible-endpoint/v1
BENCHMARK_API_PATH=/v1
BENCHMARK_MODEL=qwen3.6-35b-a3b
BENCHMARK_API_KEY=test
BENCHMARK_TIMEOUT_SECONDS=30
BENCHMARK_MAX_RETRIES=2
BENCHMARK_CONCURRENCY=16
BENCHMARK_RESULTS_DIR=tests/benchmarks/results
```

`.env` is ignored by git, while `.env.example` is tracked so the shared setup stays visible.
You can still override everything explicitly on the CLI:

```bash
python -m tests.benchmarks.ruler_multi_hop \
    --api-base "$BENCHMARK_API_BASE" \
    --api-path "$BENCHMARK_API_PATH" \
    --model "$BENCHMARK_MODEL" \
    --api-key "$BENCHMARK_API_KEY" \
    --max-tasks 3
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GWT_WORKSPACE_CAPACITY` | `7` | Max items in workspace |
| `GWT_BUFFER_SIZE` | `50` | Preconscious buffer size |
| `GWT_GOAL_MODULATION` | `0.3` | Goal boost strength (0-1) |
| `GWT_MIN_ACTIVATION` | `0.2` | Ignition threshold for admitting new workspace candidates |
| `GWT_EMBEDDING_PROVIDER` | `sentence-transformer` | `sentence-transformer` or deterministic local `hash` |
| `GWT_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence transformer model |
| `GWT_EMBEDDING_DIM` | `384` | Vector dimension for storage/search |
| `GWT_DATA_DIR` | `~/.gwt-context` | Storage directory |
| `GWT_DB_PATH` | unset | Optional exact SQLite DB path override |
| `GWT_VECTOR_INDEX_PATH` | unset | Optional exact vector index path override |
| `GWT_MAX_BROADCAST_TOKENS` | `4000` | Max tokens per broadcast |
| `GWT_MAX_VECTOR_ELEMENTS` | `100000` | Max vector index capacity setting |

## References

- Baars, B.J. (1988). *A Cognitive Theory of Consciousness*
- Hsieh et al. (2024). *RULER: What's the Real Context Size of Your Long-Context Language Models?*
- Dehaene & Naccache (2001). *Towards a cognitive neuroscience of consciousness*

## License

MIT
