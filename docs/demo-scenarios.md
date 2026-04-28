# Demo Scenarios

These scenarios are deterministic and run without downloading embedding models.
They are intended for local demos, release smoke checks, and MCP-client
workflow validation.

## 1. Graph Attention Loop

Command:

```bash
python examples/real_usage_loop.py
```

What it proves:

- facts enter long-term memory through `gwt_store`,
- `gwt_attend(planner="graph")` resolves a relation chain,
- `gwt_bus_inspect` exposes subscriber reports after the broadcast,
- `gwt_trace_explain` shows the applied bus side effects.

Expected signal:

- `graph_answer` resolves to `Paper Gamma`,
- `bus_accepted` is greater than or equal to `1`,
- `trace_status` is `ok`.

## 1a. Real MCP Stdio Smoke

Command:

```bash
python -m gwt_context.mcp_client_smoke
```

What it proves:

- `python -m gwt_context` starts as a real stdio MCP server,
- an MCP client can list tools, call tools, and read `gwt://attention/last`,
- the answer path is visible through the public protocol.

## 2. Collection Resolution

The same command also stores employee-style structured records and runs
`gwt_attend(planner="structured")` over them.

Expected signal:

- `collection_answer` returns `Ada`, the highest-scoring structured record,
- the trace includes a `resolve_answer` proposal when the broadcast contains
  enough exact evidence.

## 3. Contradiction-Aware Subscriber Flow

Command:

```bash
python examples/external_subscriber_poc.py
```

What it proves:

- external subscribers can be injected through `ExternalReasoningSubscriber`,
- proposal sanitization rewrites the subscriber name,
- `BroadcastBus` arbitrates external proposals together with local subscribers,
- provider SDKs remain outside the application layer.

Expected signal:

- accepted proposal kinds include `flag_contradiction`,
- every subscriber report has status `ok`.

## Rendering Benchmark Traces

For model-backed benchmark runs, render trace-heavy JSON as HTML:

```bash
python -m tests.benchmarks.render_trace tests/benchmarks/results/<result>.json
```

The HTML report now includes a phase timeline and compact bus health summary so
accepted actions, inhibited proposals, policy skips, and subscriber errors are
visible without reading raw JSON first.
