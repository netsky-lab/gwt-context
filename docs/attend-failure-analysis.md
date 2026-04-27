# Attend Failure Analysis

## Scope

This note summarizes the Qwen attend runs from 2026-04-27 after adding
structured collection evidence. It focuses on evidence selection and bounded
workspace behavior.

## Current Signals

- RULER advisor chains remain mostly healthy: one-pass attend reached 91.7%
  accuracy with 95.8% evidence recall on 12 tasks.
- LongBench count/filter/aggregate now passes the scoped release gate:
  100.0% GWT accuracy on 18 tasks.
- LongBench synthesis/top_k now passes the scoped release gate: 100.0% GWT
  accuracy on 12 tasks.
- Two-pass attend remains opt-in. The broad Qwen matrix did not justify making
  it the default.

## Resolved Failure Buckets

- **Counting under-selection:** fixed for structured employee records by
  creating a compressed collection evidence item instead of relying on seven
  individual workspace slots.
- **Aggregate truncation:** fixed for structured employee records by computing
  exact aggregates before broadcast and storing the supporting collection
  summary in workspace.
- **Top-k ordering:** fixed with a structured numeric resolver and deterministic
  tie-breaks by employee id.
- **Synthesis instability:** fixed for department comparisons by resolving both
  groups and broadcasting computed group averages.

## Remaining Failure Bucket

- **Multi-hop miss:** RULER still has one advisor-chain miss in the current
  12-task slice. This is a generic multi-hop selection issue, not a structured
  collection issue. It should be addressed with an advisor/entity continuation
  resolver or a better second-hop follow-up query policy.

## Design Implications

- Keep `gwt_attend(passes=1)` as the runtime default.
- Keep `passes=2` available for explicit experiments and targeted MCP calls.
- Prefer structured resolvers for tasks that require exact counting, sorting,
  or aggregation.
- Track evidence recall and precision next to answer accuracy in every
  benchmark report.
