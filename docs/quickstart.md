# Quickstart

## Install

```bash
pip install -e .
pip install -e ".[dev]"
```

For offline smoke and local demos, use deterministic hash embeddings:

```bash
export GWT_EMBEDDING_PROVIDER=hash
export GWT_EMBEDDING_MODEL=hash
```

## Run The Server

```bash
python -m gwt_context
```

The console script is also available:

```bash
gwt-context
```

## Readiness Smoke

```bash
GWT_EMBEDDING_PROVIDER=hash GWT_EMBEDDING_MODEL=hash python -m gwt_context.smoke
```

Expected output is a compact JSON report with `trace_status: "ok"` and a
resolved graph answer.

## Local Usage Loop

```bash
python examples/real_usage_loop.py
```

This in-process MCP workflow stores graph and structured records, calls
`gwt_attend`, inspects `gwt_bus_inspect`, reads `gwt_trace_explain`, and prints
a compact JSON summary.

For a broader demo checklist, see [`docs/demo-scenarios.md`](demo-scenarios.md).

## Core Tool Flow

Use `gwt_store` to persist facts:

```json
{
  "content": "Paper Alpha -> cites -> Paper Beta"
}
```

Set a goal:

```json
{
  "description": "What does Paper Alpha cite cite?",
  "keywords": ["Paper Alpha", "cites"]
}
```

Run attention in one call:

```json
{
  "question": "What does Paper Alpha cite cite?",
  "planner": "graph",
  "passes": 1
}
```

Inspect bus behavior after a broadcast or attend run:

```json
{}
```

with `gwt_bus_inspect`.

## Trace Reading

- `gwt_trace_explain` summarizes the latest `gwt_attend` run.
- `broadcast_bus` trace steps show proposals, accepted proposals, inhibited
  proposals, and subscriber execution reports.
- `broadcast_bus_tool` trace steps show applied side effects or policy skips.
- `gwt_inspect("broadcast_bus")` exposes the latest cycle-level bus read model.
- HTML trace rendering includes a phase timeline, bus action counts, policy
  skips, and subscriber status badges:

```bash
python -m tests.benchmarks.render_trace tests/benchmarks/results/<result>.json
```

## External Subscriber PoC

```bash
python examples/external_subscriber_poc.py
```

This runs `ExternalReasoningSubscriber` with a local fake agent loop so adapter
sanitization and bus arbitration can be inspected without any provider SDK.

## Benchmark Bus On/Off

Print commands:

```bash
python -m tests.benchmarks.bus_matrix --max-tasks 2
```

Run a bounded matrix:

```bash
python -m tests.benchmarks.bus_matrix --run --max-tasks 2
```

Summarize reports:

```bash
python -m tests.benchmarks.bus_matrix --summarize tests/benchmarks/results/*.json
```
