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

Release thresholds are tracked in `docs/release-thresholds.md`.

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

Latest Qwen release matrix on 2026-04-28:

| Slice | Bus | Tasks | GWT | Baseline | Avg GWT Tool Calls | Bus accepted/inhibited |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| RULER advisor/workplace/discovery | on | 12 | 100% | 100% | 3.0 | 12 / 24 |
| RULER advisor/workplace/discovery | off | 12 | 100% | 100% | 3.0 | 0 / 0 |
| LongBench count/filter/aggregate/top_k/synthesis | on | 10 | 100% | 100% | 3.0 | 10 / 10 |
| LongBench count/filter/aggregate/top_k/synthesis | off | 10 | 100% | 100% | 3.0 | 0 / 0 |

The release matrix was run with RULER chain types
`advisor/workplace/discovery`, hops `2,3`, distractors `3,10`, and LongBench
records `12,30` across all five task types. Bus subscriber timeout/error count
was `0 / 0` in all bus-on reports.

```bash
GWT_EMBEDDING_PROVIDER=hash GWT_EMBEDDING_MODEL=hash GWT_EMBEDDING_DIM=64 \
BENCHMARK_CONCURRENCY=4 BENCHMARK_ATTEND_BROADCAST_BUS=1 \
python -m tests.benchmarks.ruler_multi_hop \
  --chain-type advisor --hops 2 3 --distractors 3 10 \
  --tasks-per-config 1 --gwt-mode attend
```

Repeat for `workplace`, `discovery`, then repeat all commands with
`BENCHMARK_ATTEND_BROADCAST_BUS=0`; run LongBench with:

```bash
python -m tests.benchmarks.longbench_pro \
  --task-types count filter aggregate top_k synthesis \
  --records 12 30 --tasks-per-config 1 --gwt-mode attend
```

The current release matrix shows bus resolution activity without accuracy or
tool-call regression after deterministic `resolve_answer` suppresses
lower-priority recall queries.

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
