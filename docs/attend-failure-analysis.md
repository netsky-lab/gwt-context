# Attend Failure Analysis

## Scope

This note summarizes the Qwen attend runs from 2026-04-27 after adding the
production generic attention controller path. It focuses on evidence selection,
not model quality in isolation.

## Current Signals

- RULER advisor chains are mostly healthy: one-pass attend reached 91.7%
  accuracy with 95.8% evidence recall on 12 tasks.
- LongBench count/filter/aggregate improved on structured department queries
  but remains below prompt-only baseline: 77.8% vs 100.0% on the refreshed
  18-task run.
- LongBench synthesis/top_k is not ready as a generic-planner target: one-pass
  attend reached 25.0% vs 50.0% prompt-only baseline on the refreshed 12-task
  run.
- Two-pass attend is useful as an experiment, but not as the default. The
  2026-04-27 two-pass run increased average tool calls from 8.0 to about 12
  and did not improve accuracy on the refreshed matrix.

## Failure Buckets

- **Multi-hop miss:** RULER failures still happen when the first broadcast
  admits the first hop but not the next-hop fact. Follow-up entity queries help
  trace this path, but the current competition/workspace size can still leave
  the target fact outside the final workspace.
- **Counting under-selection:** count tasks fail when one or more matching
  records are missing from the seven-slot workspace. This is a selection
  capacity problem, not just final arithmetic.
- **Aggregate truncation:** average-years tasks can require more matching
  records than the workspace can hold. With a seven-slot workspace, exact
  aggregation over eight or more records is not guaranteed.
- **Top-k ordering:** semantic retrieval is the wrong primitive for exact
  top-k. The system needs a structured numeric resolver or sortable evidence
  table before this should be treated as a release gate.
- **Synthesis instability:** synthesis tasks depend on comparing two groups.
  Generic semantic queries often retrieve partial evidence for each group, so
  the final answer can be confident but under-supported.

## Design Implications

- Keep `gwt_attend(passes=1)` as the runtime default.
- Keep `passes=2` available for explicit experiments and targeted MCP calls.
- Add specialized resolver hooks for exact aggregation/top-k before using those
  tasks as production acceptance criteria for generic attention.
- Track evidence recall and precision next to answer accuracy in every
  benchmark report.
