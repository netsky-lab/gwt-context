# Release Baseline

## 2026-04-27 Status

The current code is a reasonable **internal deploy candidate** for local MCP
usage and benchmark iteration. It is **not production-ready** as a reliability
claim for generic long-context reasoning yet.

## Current Benchmark Baseline

Primary one-pass attend runs:

| Benchmark | Scope | GWT | Baseline | Evidence recall | Evidence precision | Artifact |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| RULER multi-hop | 12 advisor-chain tasks | 91.7% | 100.0% | 95.8% | 34.5% | `tests/benchmarks/results/ruler_multi_hop_qwen3.6-35b-a3b_20260427_140423_457145_12d146c65aa6.json` |
| LongBench Pro | count/filter/aggregate, 18 tasks | 77.8% | 100.0% | 72.8% | 30.2% | `tests/benchmarks/results/longbench_pro_qwen3.6-35b-a3b_20260427_140423_480530_12d146c65aa6.json` |
| LongBench Pro | synthesis/top_k, 12 tasks | 25.0% | 50.0% | 37.5% | 29.8% | `tests/benchmarks/results/longbench_pro_qwen3.6-35b-a3b_20260427_140423_448442_12d146c65aa6.json` |

Two-pass attend was also measured and remains experimental:

| Benchmark | Scope | GWT | Baseline | Avg tool calls | Artifact |
| --- | --- | ---: | ---: | ---: | --- |
| RULER multi-hop | 12 advisor-chain tasks | 83.3% | 100.0% | 12.2 | `tests/benchmarks/results/ruler_multi_hop_qwen3.6-35b-a3b_20260427_135900_632732_12d146c65aa6.json` |
| LongBench Pro | count/filter/aggregate, 18 tasks | 72.2% | 88.9% | 11.9 | `tests/benchmarks/results/longbench_pro_qwen3.6-35b-a3b_20260427_135900_654597_12d146c65aa6.json` |
| LongBench Pro | synthesis/top_k, 12 tasks | 50.0% | 66.7% | 11.9 | `tests/benchmarks/results/longbench_pro_qwen3.6-35b-a3b_20260427_135900_624355_12d146c65aa6.json` |

The formatted comparison report is in
`tests/benchmarks/reports/2026-04-27-qwen-attend-release-baseline.md`.

## Deploy Readiness

Internal/local deploy can proceed if the verification suite stays green:

- `pytest`
- `ruff check .`
- `mypy src`
- `npm test`
- `npm run benchmark:smoke`
- `python examples/mcp_demo.py`
- MCP boundary grep checks from `AGENTS.md`

Production deploy should wait for:

- Exact aggregation/top-k resolver support, or explicit exclusion of those task
  classes from reliability claims.
- A clean MCP runtime smoke against the intended deployed client.
- A persistence/data-dir plan for `GWT_DATA_DIR`, `GWT_DB_PATH`, and vector
  index files.
- A release tag with the benchmark report and verification logs referenced.
- Acceptance thresholds for accuracy and evidence recall by benchmark family.

## Rollback Condition

Rollback this release candidate if MCP payloads regress, boundary checks fail,
or one-pass attend drops below the current RULER 91.7% / LongBench 77.8%
reference without a documented tradeoff.
