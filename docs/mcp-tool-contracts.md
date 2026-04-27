# MCP Tool Contracts

These contracts describe the stable response shapes that MCP clients should
expect. Fields may gain additive metadata, but existing keys should not be
removed without updating tests and changelog.

## Tools

- `gwt_store(content, memory_type="semantic", tags?, link_to?)`
  - Success keys: `id`, `memory_type`, `activation_state`, `linked_to`, `status`
  - Error keys: `error`
- `gwt_set_goal(description, keywords?, priority=1.0)`
  - Success keys: `goal_id`, `description`, `priority`, `status`
- `gwt_broadcast()`
  - Returns workspace broadcast text.
- `gwt_compete(n_slots?)`
  - Success keys: `winners`, `would_evict`, `all_scores`
- `gwt_query(query, k=5, memory_type?, admit=false)`
  - Success item keys: `id`, `content`, `memory_type`, `activation_state`,
    `activation_level`, `linked_ids`, `tags`, `admitted`
  - Error keys: `error`, optional `supported_memory_types`
- `gwt_attend(question, keywords?, k=5, passes=1, planner="auto", admit=true)`
  - Success keys: `question`, `planner`, `supported_planners`, `context_count`,
    `passes_requested`, `passes_completed`, `admit`, `evidence_plan`,
    `tool_call_count`, `admitted_ids`, `broadcast`, `workspace`, `trace`
  - Error keys: `error`, optional `supported_planners`
- `gwt_resolve(question, planner="auto", k=50)`
  - Success keys: `question`, `planner`, `context_count`, `evidence_plan`
  - Error keys: `error`, optional `supported_planners`
- `gwt_collection_query(operation, field?, value?, metric?, k=5, group_field?, group_a?, group_b?)`
  - Success keys: `operation`, `answer`, `matched_count`, `matched_records`,
    `supporting_evidence`, `metadata`
  - Error keys: `error`, optional `supported_operations`
- `gwt_trace_explain()`
  - Success keys: `status`, `question`, `planner`, `strategy`, `answer`,
    `pass_count`, `tool_call_count`, `phases`, `broadcast_bus`,
    `explanation`, `trace`
  - Empty keys: `status`, `message`
- `gwt_evict(item_id)`
  - Delegates to `CyclePort.evict_workspace_item`; payload is cycle-defined.
- `gwt_link(source_id, target_id)`
  - Delegates to `CyclePort.link_items`; payload is cycle-defined.
- `gwt_inspect(target="workspace")`
  - Delegates to `CyclePort.inspect`; payload is target-specific read model.
  - `target="broadcast_bus"` returns whether the cycle bus is configured, the
    latest bus result, and linked-memory reactivations from the latest cycle.

## Evidence Plan Shape

Tools that return `evidence_plan` use:

```json
{
  "strategy": "string",
  "answer": "string",
  "queries": ["string"],
  "evidence": ["string"],
  "metadata": {}
}
```

Planner names are `auto`, `generic`, `semantic`, `structured`, `graph`, and
`hybrid`.
