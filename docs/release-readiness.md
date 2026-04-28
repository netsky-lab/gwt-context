# Release Readiness

Status as of 2026-04-27: release candidate for local MCP use and bounded
OpenAI-compatible benchmark evaluation.

## What Is Ready

- MCP server startup through `python -m gwt_context` and `gwt-context`.
- Offline readiness smoke through `python -m gwt_context.smoke` or
  `gwt-context-smoke`.
- Runtime tools for store/query/broadcast, explicit attend, exact resolve,
  collection query, relation graph paths, trace explanation, link/evict/inspect.
- Cycle-level post-broadcast subscriber bus for independent structured resolve,
  semantic recall, relation continuation, contradiction checking, and plan
  critique proposals. `gwt_attend` applies accepted proposal kinds through
  public ports or evidence-plan metadata.
- Workspace ignition threshold through `GWT_MIN_ACTIVATION`; weak candidates
  remain preconscious instead of filling empty slots automatically.
- Recurrent link activation: conscious items enqueue their linked memories for
  the next cycle.
- Subscriber execution reports for `ok`, `timeout`, and `error` statuses, plus
  a dedicated `gwt_bus_inspect` MCP tool.
- Bus on/off matrix helper:
  `python -m tests.benchmarks.bus_matrix --run --max-tasks N`.
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

Bus matrix summary:

```bash
python -m tests.benchmarks.bus_matrix --summarize tests/benchmarks/results/*.json
```

## Qwen Smoke

Bounded model-backed smoke uses production `attend` mode and deterministic local
GWT embeddings:

```bash
GWT_EMBEDDING_PROVIDER=hash GWT_EMBEDDING_MODEL=hash GWT_EMBEDDING_DIM=64 \
BENCHMARK_CONCURRENCY=1 \
BENCHMARK_ATTEND_BROADCAST_BUS=1 \
python -m tests.benchmarks.ruler_multi_hop \
  --chain-type advisor --hops 2 --distractors 3 10 \
  --tasks-per-config 1 --max-tasks 2 --gwt-mode attend
```

Repeat with `--chain-type workplace` and `--chain-type discovery`, then run:

```bash
GWT_EMBEDDING_PROVIDER=hash GWT_EMBEDDING_MODEL=hash GWT_EMBEDDING_DIM=64 \
BENCHMARK_CONCURRENCY=1 \
BENCHMARK_ATTEND_BROADCAST_BUS=1 \
python -m tests.benchmarks.longbench_pro \
  --task-types count filter aggregate top_k synthesis \
  --records 12 --tasks-per-config 1 --max-tasks 5 --gwt-mode attend
```

Latest bounded Qwen smoke on 2026-04-27:

| Slice | Bus | Tasks | GWT | Baseline | Avg GWT Tool Calls | Bus accepted/inhibited |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| RULER advisor | on | 2 | 100% | 100% | 3.0 | 2 / 4 |
| RULER advisor | off | 2 | 100% | 100% | 3.0 | 0 / 0 |
| LongBench count/filter smoke | on | 2 | 100% | 100% | 3.0 | 2 / 2 |
| LongBench count/filter smoke | off | 2 | 100% | 100% | 3.0 | 0 / 0 |

The latest bounded matrix was run with:

```bash
python -m tests.benchmarks.bus_matrix --run --max-tasks 2
```

The current bounded slices show bus resolution activity without extra tool-call
cost after deterministic `resolve_answer` suppresses lower-priority recall
queries. LongBench bus-on doubled evidence precision on the count/filter smoke
slice (28.6% vs 14.3%) with no accuracy/tool-call regression. This is still a
small smoke, not a full regression matrix.

Benchmark JSON outputs are generated under ignored `tests/benchmarks/results/`
and must not be committed.

To measure the bus itself, repeat the same commands with
`BENCHMARK_ATTEND_BROADCAST_BUS=0` and compare accuracy, tool calls, and trace
proposal counts against the default bus-on run.

## Remaining Non-Blockers

- Larger benchmark matrix with more distractors, more records, and multiple
  random seeds.
- Publishing to PyPI or an internal package registry.
- Hosted documentation for MCP client configuration examples.
