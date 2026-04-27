# Release Readiness

Status as of 2026-04-27: release candidate for local MCP use and bounded
OpenAI-compatible benchmark evaluation.

## What Is Ready

- MCP server startup through `python -m gwt_context` and `gwt-context`.
- Offline readiness smoke through `python -m gwt_context.smoke` or
  `gwt-context-smoke`.
- Runtime tools for store/query/broadcast, explicit attend, exact resolve,
  collection query, relation graph paths, trace explanation, link/evict/inspect.
- Post-broadcast subscriber bus for independent structured resolve, semantic
  recall, relation continuation, contradiction checking, and plan critique
  proposals.
- Deterministic hash embeddings for local smoke and CI without downloading a
  sentence-transformer model.
- Qwen/OpenAI-compatible benchmark entrypoints for RULER and LongBench Pro.

## Verification Gates

Required local gates before release:

```bash
pytest -q
ruff check .
mypy src
npm test -- --quiet
python -m gwt_context.smoke
python -m build
```

Boundary checks:

```bash
rg -n "cycle\.(workspace|buffer|goal_manager)|_cycle\.(workspace|buffer|goal_manager)|from gwt_context\.infrastructure|tests\.benchmarks" src/gwt_context/mcp src/gwt_context/application || true
git ls-files | rg -n "(tests/benchmarks/(results|reports)|tests/benchmarks/.*\.log|\.env$|supervisor|\.benchmarks|\.worktrees)" || true
git grep -n "proxy\.runpod\.net" HEAD -- . ':!research' || true
```

## Qwen Smoke

Bounded model-backed smoke uses production `attend` mode and deterministic local
GWT embeddings:

```bash
GWT_EMBEDDING_PROVIDER=hash GWT_EMBEDDING_MODEL=hash GWT_EMBEDDING_DIM=64 \
BENCHMARK_CONCURRENCY=1 \
python -m tests.benchmarks.ruler_multi_hop \
  --chain-type advisor --hops 2 --distractors 3 10 \
  --tasks-per-config 1 --max-tasks 2 --gwt-mode attend
```

Repeat with `--chain-type workplace` and `--chain-type discovery`, then run:

```bash
GWT_EMBEDDING_PROVIDER=hash GWT_EMBEDDING_MODEL=hash GWT_EMBEDDING_DIM=64 \
BENCHMARK_CONCURRENCY=1 \
python -m tests.benchmarks.longbench_pro \
  --task-types count filter aggregate top_k synthesis \
  --records 12 --tasks-per-config 1 --max-tasks 5 --gwt-mode attend
```

Latest bounded Qwen smoke on 2026-04-27:

| Slice | Tasks | GWT | Baseline | Avg GWT Tool Calls |
| --- | ---: | ---: | ---: | ---: |
| RULER advisor | 2 | 100% | 100% | 3.0 |
| RULER workplace | 2 | 100% | 100% | 3.0 |
| RULER discovery | 2 | 100% | 100% | 3.0 |
| LongBench count/filter/aggregate/top_k/synthesis | 5 | 100% | 100% | 3.0 |

Benchmark JSON outputs are generated under ignored `tests/benchmarks/results/`
and must not be committed.

## Remaining Non-Blockers

- Larger benchmark matrix with more distractors, more records, and multiple
  random seeds.
- Publishing to PyPI or an internal package registry.
- Hosted documentation for MCP client configuration examples.
