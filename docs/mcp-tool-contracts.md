# MCP Tool Contracts

These contracts describe the stable response shapes that MCP clients should
expect. Fields may gain additive metadata, but existing keys should not be
removed without updating tests and changelog.

## Tools

- `gwt_store(content, memory_type="semantic", tags?, link_to?)`
  - Success keys: `id`, `memory_type`, `activation_state`, `linked_to`, `tags`,
    `status`
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
- `gwt_bus_inspect()`
  - Success keys: `status`, `broadcast_bus`, `summary`
  - `summary` includes proposal, accepted, inhibited, and subscriber status
    counts from the latest cycle-level bus read model, plus inhibited reason
    counts and proposal grouping data when a bus result exists.
- `gwt_memory_profile()`
  - Success keys: `status`, `namespace`, `data_dir`, `embedding`,
    `persisted_item_count`, `runtime_index_count`, `structured_record_count`,
    `structured_fields`, `counts_by_type`, `counts_by_source`,
    `restored_runtime_items`, `cycle_stats`, `retention_policy`
- `gwt_export_memory(memory_type?, tag?)`
  - Success keys: `status`, `format`, `item_count`, `filters`, `jsonl`
  - Format is `gwt-memory-jsonl-v1`; embeddings are intentionally omitted and
    rebuilt during import.
  - Error keys: `error`, optional `supported_memory_types`
- `gwt_import_memory(jsonl, default_memory_type="semantic", tags?, admit=false)`
  - Success keys: `status`, `imported_count`, `imported_ids`, `error_count`,
    `errors`, `admit`
  - Imported records receive active namespace tags and are re-embedded into the
    current namespace.
  - Error keys: `error`, optional `supported_memory_types`
- `gwt_reset(scope="runtime", confirm="")`
  - Supported scopes: `runtime`, `workspace`.
  - Runtime reset requires `confirm="RESET_RUNTIME"` and clears only in-process
    structured read models.
  - Workspace reset requires `confirm="RESET_WORKSPACE"` and evicts current
    workspace items through `CyclePort`.
  - Persistent namespace deletion remains outside MCP in local maintenance
    scripts.
- `gwt_evict(item_id)`
  - Delegates to `CyclePort.evict_workspace_item`; payload is cycle-defined.
- `gwt_link(source_id, target_id)`
  - Delegates to `CyclePort.link_items`; payload is cycle-defined.
- `gwt_inspect(target="workspace")`
  - Delegates to `CyclePort.inspect`; payload is target-specific read model.
  - `target="broadcast_bus"` returns whether the cycle bus is configured, the
    latest bus result, summary, proposal groups, and linked-memory reactivations
    from the latest cycle.

## Broadcast Bus Result Shape

Serialized bus results include `proposals`, `accepted`, `inhibited`,
`decisions`, `summary`, `proposal_groups`, and `subscriber_reports`.

`decisions` records one arbitration outcome per accepted or inhibited proposal:

```json
{
  "status": "accepted",
  "reason": "accepted",
  "proposal": {}
}
```

Current inhibition reason codes are `below_threshold`, `duplicate_key`,
`max_accepted`, and `resolved_answer_present`.

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
