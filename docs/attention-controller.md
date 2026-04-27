# Attention Controller Architecture Note

## Decision

Use an explicit attention controller plus pluggable evidence resolvers for
selection/admission, and keep free-form model tool loops as an experimental
mode rather than the primary reliability path.

## Why

The Qwen four-mode matrix shows that larger context and raw tool access are not
enough. In `tools` mode, failures cluster around tool-loop behavior:
tool-call markup emitted as an answer, max tool rounds, and wrong answers after
tool use. Controlled and hybrid modes fix the selection/admission step before
the model reasons.

The architecture now separates concerns:

- `AttentionController` performs the reusable GWT loop through application
  ports: set goal, plan queries, admit matches, broadcast.
- Production MCP uses a generic semantic query planner through `gwt_attend`.
- Benchmarks use task-specific resolver adapters under `tests/benchmarks/`.
- Hybrid mode lets the model synthesize from selected evidence without letting
  it control the whole tool loop.

## Implications

- Runtime MCP code must not import benchmark resolvers.
- Resolver quality becomes measurable through evidence precision/recall, not
  only final answer accuracy.
- Free-form tools mode remains valuable for studying agent behavior, but
  regressions should be classified by failure bucket before changing storage or
  competition logic.

## Regression Gates

- `pytest` for deterministic controller, MCP, and benchmark smoke coverage.
- `python -m tests.benchmarks.regression_smoke` for generated benchmark task
  shape without external model calls.
- Four-mode benchmark reports for model-backed changes that affect selection,
  admission, or prompt/tool schema behavior.
