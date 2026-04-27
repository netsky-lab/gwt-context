# Release Baseline

## 2026-04-27 Status

The current code is a **deploy candidate for scoped MCP usage**:

- supported claim: goal-directed attend for RULER-style advisor chains and
  structured employee collection tasks;
- unsupported claim: arbitrary generic long-context reasoning without a
  resolver or structured evidence path.

The remaining known gap is one RULER advisor-chain miss in the 12-task Qwen
slice. The structured LongBench slices now pass the release gates.

## Current Benchmark Baseline

Primary one-pass attend runs:

| Benchmark | Scope | GWT | Baseline | Evidence recall | Evidence precision |
| --- | --- | ---: | ---: | ---: | ---: |
| RULER multi-hop | 12 advisor-chain tasks | 91.7% | 100.0% | 95.8% | 34.5% |
| LongBench Pro | count/filter/aggregate, 18 tasks | 100.0% | 100.0% | 100.0% | 45.9% |
| LongBench Pro | synthesis/top_k, 12 tasks | 100.0% | 75.0% | 100.0% | 40.5% |

Raw benchmark JSON and formatted reports are local generated artifacts and are
ignored by git under `tests/benchmarks/results/` and `tests/benchmarks/reports/`.

## Release Gates

| Gate | Threshold | Current | Status |
| --- | ---: | ---: | --- |
| RULER advisor chains | 90.0% | 91.7% | pass |
| Count | 90.0% | 100.0% | pass |
| Filter | 90.0% | 100.0% | pass |
| Aggregate | 90.0% | 100.0% | pass |
| Synthesis | 80.0% | 100.0% | pass |
| Top-k | 80.0% | 100.0% | pass |

## Deploy Readiness

Proceed with push/deploy if the verification suite stays green:

- `pytest`
- `ruff check .`
- `mypy src`
- `npm test`
- `npm run benchmark:smoke`
- `python examples/mcp_demo.py`
- `GWT_DATA_DIR=$(mktemp -d) timeout 5 python -m gwt_context < /dev/null`
- MCP boundary grep checks from `AGENTS.md`

Before a public production claim, also decide the persistence policy for
`GWT_DATA_DIR`, `GWT_DB_PATH`, and vector index files in the target environment.

## Rollback Condition

Rollback this release candidate if MCP payloads regress, boundary checks fail,
or one-pass attend drops below the current RULER 91.7% / LongBench structured
100.0% reference without a documented tradeoff.
