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

## MCP Tools

| Tool | Description |
|------|------------|
| `gwt_store` | Store content in long-term memory (embed + index + buffer) |
| `gwt_set_goal` | Set active goal — biases competition toward goal-relevant items |
| `gwt_broadcast` | Run selection-broadcast cycle — returns workspace content |
| `gwt_compete` | Competition round without broadcast (dry-run) |
| `gwt_query` | Semantic search over long-term memory |
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
│   ├── cycle.py      # SelectionBroadcastCycle + PreconsciousBuffer
│   ├── ingestion.py  # Content → MemoryItem pipeline
│   └── goal_manager.py
├── infrastructure/   # Storage, embeddings
│   ├── storage.py    # SQLiteMemoryStore
│   ├── vector_index.py # Numpy cosine similarity index
│   ├── embeddings.py # SentenceTransformerEmbedder
│   └── config.py     # GWTConfig
├── mcp/              # MCP interface
│   ├── tools.py      # 8 tool definitions
│   ├── resources.py  # MCP resources
│   └── prompts.py    # System + multi-hop prompts
└── server.py         # FastMCP wiring + entry point
```

## Tests

```bash
pip install -e ".[dev]"
pytest tests/unit/ tests/integration/ -q
```

67 tests covering domain logic, storage, vector index, and full selection-broadcast cycles.

## Benchmarks

Benchmark harness for evaluation against OpenAI-compatible APIs (Qwen, Llama, etc. via vLLM/TGI):

```bash
# RULER multi-hop (2-4 hops, scattered needles in haystack)
python -m tests.benchmarks.ruler_multi_hop \
    --api-base http://localhost:8000/v1 \
    --model Qwen/Qwen3-235B-A22B

# LongBench Pro aggregation (count, filter, aggregate over records)
python -m tests.benchmarks.longbench_pro \
    --api-base http://localhost:8000/v1 \
    --model Qwen/Qwen3-235B-A22B
```

Each benchmark runs GWT mode (with tools) and baseline mode (all context in prompt) for comparison. Results saved as JSON in `tests/benchmarks/results/`.

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GWT_WORKSPACE_CAPACITY` | `7` | Max items in workspace |
| `GWT_BUFFER_SIZE` | `50` | Preconscious buffer size |
| `GWT_GOAL_MODULATION` | `0.3` | Goal boost strength (0-1) |
| `GWT_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence transformer model |
| `GWT_DATA_DIR` | `~/.gwt-context` | Storage directory |
| `GWT_MAX_BROADCAST_TOKENS` | `4000` | Max tokens per broadcast |

## References

- Baars, B.J. (1988). *A Cognitive Theory of Consciousness*
- Hsieh et al. (2024). *RULER: What's the Real Context Size of Your Long-Context Language Models?*
- Dehaene & Naccache (2001). *Towards a cognitive neuroscience of consciousness*

## License

MIT
