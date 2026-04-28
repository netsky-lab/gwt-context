"""MCP tool definitions for GWT-Context.

MCP tools that form the external API surface for LLM interaction.
Each tool maps to domain/application operations.
"""

import json
import os
from collections.abc import Sequence
from typing import Any

from mcp.server.fastmcp import FastMCP

from gwt_context.application.attention import (
    AttentionController,
    AttentionTraceStore,
    GenericEvidenceResolver,
    attention_run_to_dict,
    evidence_plan_to_dict,
    supported_planners,
)
from gwt_context.application.structured import RuntimeMemoryIndex, StructuredRecord
from gwt_context.domain.models import MemoryItem, MemoryType
from gwt_context.interfaces.ports import CyclePort, IngestionPort


def register_tools(
    mcp: FastMCP,
    cycle: CyclePort,
    ingestion: IngestionPort,
    attention_trace: AttentionTraceStore | None = None,
) -> None:
    """Register all GWT tools on the MCP server."""
    runtime_index = RuntimeMemoryIndex()
    restored_count = _restore_runtime_index(runtime_index, ingestion)

    @mcp.tool()
    def gwt_store(
        content: str,
        memory_type: str = "semantic",
        tags: list[str] | None = None,
        link_to: list[str] | None = None,
    ) -> dict[str, Any]:
        """Store information in long-term memory and make it eligible for workspace competition.

        Use this to save important facts, observations, reasoning results,
        or any information you want to persist and potentially broadcast later.

        Args:
            content: The text content to store.
            memory_type: One of: episodic, semantic, procedural, working.
            tags: Optional tags for categorization.
            link_to: Optional list of memory item IDs to link to (enables multi-hop chains).
        """
        if not content.strip():
            return {"error": "content must not be empty"}
        mt = _parse_memory_type(memory_type) or MemoryType.SEMANTIC

        item = ingestion.ingest(
            content=content,
            memory_type=mt,
            source="tool:gwt_store",
            tags=_memory_tags(tags),
            link_to=link_to,
        )

        cycle.enqueue_for_competition(item)
        runtime_index.add(item.content or content)

        return {
            "id": item.id,
            "memory_type": item.memory_type.value,
            "activation_state": item.activation_state.value,
            "linked_to": item.linked_ids,
            "tags": item.tags,
            "status": "stored and ready for competition",
        }

    @mcp.tool()
    def gwt_memory_profile() -> dict[str, Any]:
        """Inspect the active MCP memory namespace and runtime read models."""
        items = ingestion.all_items()
        by_type: dict[str, int] = {}
        by_source: dict[str, int] = {}
        for item in items:
            by_type[item.memory_type.value] = by_type.get(item.memory_type.value, 0) + 1
            source = item.source or "unknown"
            by_source[source] = by_source.get(source, 0) + 1

        runtime_collection = runtime_index.collection()
        namespace = _memory_namespace()
        return {
            "status": "ok",
            "namespace": namespace,
            "data_dir": namespace["data_dir"],
            "embedding": {
                "provider": os.environ.get("GWT_EMBEDDING_PROVIDER", "hash"),
                "model": os.environ.get("GWT_EMBEDDING_MODEL", "hash"),
                "dim": os.environ.get("GWT_EMBEDDING_DIM"),
            },
            "persisted_item_count": len(items),
            "runtime_index_count": len(runtime_index.contents()),
            "structured_record_count": len(runtime_collection.records),
            "structured_fields": list(runtime_collection.field_names),
            "counts_by_type": by_type,
            "counts_by_source": by_source,
            "file_sizes": _namespace_file_sizes(namespace["data_dir"]),
            "restored_runtime_items": restored_count,
            "cycle_stats": cycle.inspect(target="stats"),
            "retention_policy": {
                "working_memory_recommendation": (
                    "Keep working summaries short-lived; export useful records as semantic "
                    "or procedural memory, then reset the runtime read model."
                ),
                "persistent_cleanup": "Use scripts/clear_codex_memory.py for namespace deletion.",
            },
        }

    @mcp.tool()
    def gwt_reset(scope: str = "runtime", confirm: str = "") -> dict[str, Any]:
        """Reset runtime MCP read models with an explicit confirmation string.

        This tool never deletes persisted SQLite/vector memory. Persistent namespace
        deletion is intentionally kept in local scripts, outside MCP.
        """
        normalized_scope = scope.lower().strip() or "runtime"
        if normalized_scope == "runtime":
            if confirm != "RESET_RUNTIME":
                return {
                    "error": "confirmation required",
                    "required_confirm": "RESET_RUNTIME",
                    "scope": "runtime",
                }
            before = len(runtime_index.contents())
            runtime_index.clear()
            return {
                "status": "reset",
                "scope": "runtime",
                "cleared_runtime_items": before,
                "persistent_memory_deleted": False,
            }

        if normalized_scope == "workspace":
            if confirm != "RESET_WORKSPACE":
                return {
                    "error": "confirmation required",
                    "required_confirm": "RESET_WORKSPACE",
                    "scope": "workspace",
                }
            workspace = cycle.inspect(target="workspace")
            items = workspace.get("items", []) if isinstance(workspace, dict) else []
            evicted: list[str] = []
            for workspace_item in items:
                item_id = workspace_item.get("id") if isinstance(workspace_item, dict) else None
                if isinstance(item_id, str) and item_id:
                    result = cycle.evict_workspace_item(item_id=item_id)
                    if result.get("status") == "evicted":
                        evicted.append(item_id)
            return {
                "status": "reset",
                "scope": "workspace",
                "evicted_ids": evicted,
                "persistent_memory_deleted": False,
            }

        if normalized_scope == "persistent":
            if confirm != "RESET_PERSISTENT":
                return {
                    "error": "confirmation required",
                    "required_confirm": "RESET_PERSISTENT",
                    "scope": "persistent",
                }
            items = ingestion.all_items()
            backup_jsonl = "\n".join(
                json.dumps(_export_item(item), sort_keys=True) for item in items
            )
            deleted_count = ingestion.delete_items([item.id for item in items])
            runtime_index.clear()
            return {
                "status": "reset",
                "scope": "persistent",
                "deleted_count": deleted_count,
                "persistent_memory_deleted": True,
                "backup": {
                    "format": "gwt-memory-jsonl-v1",
                    "item_count": len(items),
                    "jsonl": backup_jsonl,
                },
            }

        return {
            "error": f"unsupported reset scope: {scope}",
            "supported_scopes": ["runtime", "workspace", "persistent"],
        }

    @mcp.tool()
    def gwt_backup_memory(
        memory_type: str | None = None,
        tag: str | None = None,
    ) -> dict[str, Any]:
        """Create a JSONL backup payload for the active memory namespace."""
        exported = gwt_export_memory(memory_type=memory_type, tag=tag)
        if "error" in exported:
            return dict(exported)
        namespace = _memory_namespace()
        return {
            "status": "ok",
            "format": "gwt-memory-backup-v1",
            "namespace": namespace,
            "file_sizes": _namespace_file_sizes(namespace["data_dir"]),
            "item_count": exported["item_count"],
            "jsonl": exported["jsonl"],
        }

    @mcp.tool()
    def gwt_restore_memory(
        jsonl: str,
        mode: str = "merge",
        confirm: str = "",
        admit: bool = False,
    ) -> dict[str, Any]:
        """Restore JSONL memory into the active namespace.

        `mode="replace"` deletes existing persisted memory first and requires
        `confirm="RESTORE_REPLACE"`. `mode="merge"` keeps existing memory.
        """
        normalized_mode = mode.lower().strip() or "merge"
        if normalized_mode not in {"merge", "replace"}:
            return {
                "error": f"unsupported restore mode: {mode}",
                "supported_modes": ["merge", "replace"],
            }
        deleted_count = 0
        backup: dict[str, Any] | None = None
        if normalized_mode == "replace":
            if confirm != "RESTORE_REPLACE":
                return {
                    "error": "confirmation required",
                    "required_confirm": "RESTORE_REPLACE",
                    "mode": "replace",
                }
            existing = ingestion.all_items()
            backup = {
                "format": "gwt-memory-jsonl-v1",
                "item_count": len(existing),
                "jsonl": "\n".join(
                    json.dumps(_export_item(item), sort_keys=True) for item in existing
                ),
            }
            deleted_count = ingestion.delete_items([item.id for item in existing])
            runtime_index.clear()
        imported = _import_memory_jsonl(
            jsonl=jsonl,
            default_memory_type=MemoryType.SEMANTIC,
            tags=None,
            admit=admit,
            dedupe=True,
            ingestion=ingestion,
            cycle=cycle,
            runtime_index=runtime_index,
        )
        imported["mode"] = normalized_mode
        imported["deleted_count"] = deleted_count
        if backup is not None:
            imported["backup"] = backup
        return imported

    @mcp.tool()
    def gwt_compact_working_memory(
        max_items: int = 20,
        dry_run: bool = True,
        confirm: str = "",
    ) -> dict[str, Any]:
        """Compact old working-memory records into one semantic summary item.

        By default this is a dry run. Deletion requires
        `dry_run=false` and `confirm="COMPACT_WORKING"`.
        """
        if max_items < 0:
            return {"error": "max_items must be >= 0"}
        working_items = sorted(
            [
                item for item in ingestion.all_items()
                if item.memory_type == MemoryType.WORKING
            ],
            key=lambda item: item.created_at,
            reverse=True,
        )
        keep = working_items[:max_items]
        compact = working_items[max_items:]
        backup_jsonl = "\n".join(json.dumps(_export_item(item), sort_keys=True) for item in compact)
        if dry_run:
            return {
                "status": "dry_run",
                "max_items": max_items,
                "keep_count": len(keep),
                "compact_count": len(compact),
                "candidate_ids": [item.id for item in compact],
                "backup": {
                    "format": "gwt-memory-jsonl-v1",
                    "item_count": len(compact),
                    "jsonl": backup_jsonl,
                },
            }
        if confirm != "COMPACT_WORKING":
            return {
                "error": "confirmation required",
                "required_confirm": "COMPACT_WORKING",
            }
        summary_item: MemoryItem | None = None
        if compact:
            summary_item = ingestion.ingest(
                content=_working_summary_content(compact),
                memory_type=MemoryType.SEMANTIC,
                source="tool:gwt_compact_working_memory",
                tags=_memory_tags(["compaction:working"]),
            )
            runtime_index.add(summary_item.content)
        deleted_count = ingestion.delete_items([item.id for item in compact])
        return {
            "status": "compacted",
            "max_items": max_items,
            "keep_count": len(keep),
            "deleted_count": deleted_count,
            "summary_id": summary_item.id if summary_item else None,
            "backup": {
                "format": "gwt-memory-jsonl-v1",
                "item_count": len(compact),
                "jsonl": backup_jsonl,
            },
        }

    @mcp.tool()
    def gwt_export_memory(
        memory_type: str | None = None,
        tag: str | None = None,
    ) -> dict[str, Any]:
        """Export persisted memory records as JSONL without embeddings."""
        mt = _parse_memory_type(memory_type)
        if memory_type and mt is None:
            return {
                "error": f"unsupported memory_type: {memory_type}",
                "supported_memory_types": [item.value for item in MemoryType],
            }
        items = [
            item for item in ingestion.all_items()
            if (mt is None or item.memory_type == mt) and (tag is None or tag in item.tags)
        ]
        jsonl = "\n".join(json.dumps(_export_item(item), sort_keys=True) for item in items)
        return {
            "status": "ok",
            "format": "gwt-memory-jsonl-v1",
            "item_count": len(items),
            "filters": {"memory_type": memory_type, "tag": tag},
            "jsonl": jsonl,
        }

    @mcp.tool()
    def gwt_import_memory(
        jsonl: str,
        default_memory_type: str = "semantic",
        tags: list[str] | None = None,
        admit: bool = False,
        dedupe: bool = True,
    ) -> dict[str, Any]:
        """Import JSONL memory records, re-embedding them into the active namespace."""
        default_mt = _parse_memory_type(default_memory_type)
        if default_mt is None:
            return {
                "error": f"unsupported default_memory_type: {default_memory_type}",
                "supported_memory_types": [item.value for item in MemoryType],
            }
        if not jsonl.strip():
            return {"error": "jsonl must not be empty"}
        return _import_memory_jsonl(
            jsonl=jsonl,
            default_memory_type=default_mt,
            tags=tags,
            admit=admit,
            dedupe=dedupe,
            ingestion=ingestion,
            cycle=cycle,
            runtime_index=runtime_index,
        )

    @mcp.tool()
    def gwt_set_goal(
        description: str,
        keywords: list[str] | None = None,
        priority: float = 1.0,
    ) -> dict[str, Any]:
        """Set the active goal that guides workspace competition.

        The goal modulates which memories win competition for workspace slots.
        Call this when the task objective changes or becomes clearer.

        Args:
            description: Natural language description of current objective.
            keywords: Key terms to boost in relevance matching.
            priority: Influence strength (0.1 to 2.0). Higher = stronger bias.
        """
        goal = cycle.set_goal(
            description=description,
            keywords=keywords,
            priority=priority,
        )
        return {
            "goal_id": goal.id,
            "description": goal.description,
            "priority": goal.priority,
            "status": "goal set — competition will now favor relevant items",
        }

    @mcp.tool()
    def gwt_broadcast() -> str:
        """Run the full GWT selection-broadcast cycle.

        This is the PRIMARY tool. It:
        1. Gathers candidates from the preconscious buffer and vector search
        2. Runs all 5 specialists to score candidates
        3. Winners compete for workspace slots (evicting weaker occupants)
        4. Returns the full workspace broadcast text

        Call this before any complex reasoning step to ensure the most
        relevant information is in your active context.
        """
        record = cycle.run()
        return record.formatted_content

    @mcp.tool()
    def gwt_compete(n_slots: int | None = None) -> dict[str, Any]:
        """Run a competition round without applying changes (dry run).

        Returns the competition results: who would win, who would be evicted,
        and all scores. Useful for inspecting what would happen.

        Args:
            n_slots: Number of workspace slots to fill (default: workspace capacity).
        """
        result = cycle.run_competition_dry(n_slots=n_slots)
        return {
            "winners": [
                {"id": w.id, "score": result.scores.get(w.id, 0), "preview": w.content[:100]}
                for w in result.winners
            ],
            "would_evict": [
                {"id": e.id, "score": result.scores.get(e.id, 0), "preview": e.content[:100]}
                for e in result.evicted
            ],
            "all_scores": {
                k: round(v, 3) for k, v in sorted(
                    result.scores.items(), key=lambda x: x[1], reverse=True
                )
            },
        }

    @mcp.tool()
    def gwt_query(
        query: str,
        k: int = 5,
        memory_type: str | None = None,
        admit: bool = False,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """Search long-term memory by semantic similarity.

        By default this returns matching items without admitting them to workspace.
        Set admit=true when the results should compete for the next broadcast.

        Args:
            query: Search query text.
            k: Number of results to return.
            memory_type: Optional filter (episodic/semantic/procedural/working).
            admit: Whether to enqueue matching items for workspace competition.
        """
        if not query.strip():
            return {"error": "query must not be empty"}
        if k < 1:
            return {"error": "k must be >= 1"}
        mt = _parse_memory_type(memory_type)
        if memory_type and mt is None:
            return {
                "error": f"unsupported memory_type: {memory_type}",
                "supported_memory_types": [item.value for item in MemoryType],
            }
        items = ingestion.query_similar(query=query, k=k, memory_type=mt)
        admitted_ids = []
        if admit:
            for item in items:
                cycle.enqueue_for_competition(item)
                admitted_ids.append(item.id)
        return [
            {
                "id": item.id,
                "content": item.content,
                "memory_type": item.memory_type.value,
                "activation_state": item.activation_state.value,
                "activation_level": round(item.activation_level, 3),
                "linked_ids": item.linked_ids,
                "tags": item.tags,
                "admitted": item.id in admitted_ids,
            }
            for item in items
        ]

    @mcp.tool()
    def gwt_attend(
        question: str,
        keywords: list[str] | None = None,
        k: int = 5,
        passes: int = 1,
        planner: str = "auto",
        admit: bool = True,
    ) -> dict[str, Any]:
        """Run explicit attention passes for the current question.

        This is a one-call path for goal-directed GWT selection:
        set the active goal, plan semantic evidence queries, admit matches into
        competition, run one or more broadcasts, and return the selected workspace.

        Args:
            question: Current task/question that should guide attention.
            keywords: Optional goal keywords. If omitted, keywords are inferred.
            k: Number of semantic matches to admit per planned query.
            passes: Maximum attention/broadcast passes to run.
            planner: Evidence planner name: auto, semantic, structured, graph, or hybrid.
            admit: Whether query matches should be admitted into competition.
        """
        normalized_planner = _normalize_supported_planner(planner)
        if normalized_planner is None:
            return {
                "error": f"unsupported planner: {planner}",
                "supported_planners": list(supported_planners()),
            }
        if passes < 1:
            return {"error": "passes must be >= 1"}
        if k < 1:
            return {"error": "k must be >= 1"}

        context_chunks = _context_chunks_for_question(
            question=question,
            k=k,
            planner=normalized_planner,
            runtime_index=runtime_index,
            ingestion=ingestion,
        )
        controller = AttentionController(
            cycle=cycle,
            ingestion=ingestion,
            resolvers=[GenericEvidenceResolver(planner=normalized_planner)],
            query_k=k,
            admit_query_results=admit,
        )
        run = controller.run(
            question=question,
            context_chunks=context_chunks,
            keywords=keywords,
            passes=passes,
        )
        trace = attention_run_to_dict(question, run)
        if attention_trace is not None:
            trace = attention_trace.record(question, run)
        return {
            "question": question,
            "planner": normalized_planner,
            "supported_planners": list(supported_planners()),
            "context_count": len(context_chunks),
            "passes_requested": passes,
            "passes_completed": run.pass_count,
            "admit": admit,
            "evidence_plan": evidence_plan_to_dict(run.evidence),
            "tool_call_count": run.tool_call_count,
            "admitted_ids": list(run.admitted_ids),
            "broadcast": run.broadcast_text,
            "workspace": cycle.inspect("workspace"),
            "trace": trace["trace"],
        }

    @mcp.tool()
    def gwt_resolve(
        question: str,
        planner: str = "auto",
        k: int = 50,
    ) -> dict[str, Any]:
        """Resolve a question against runtime structured memory without broadcasting."""
        normalized_planner = _normalize_supported_planner(planner)
        if normalized_planner is None:
            return {
                "error": f"unsupported planner: {planner}",
                "supported_planners": list(supported_planners()),
            }
        if k < 1:
            return {"error": "k must be >= 1"}

        context_chunks = _context_chunks_for_question(
            question=question,
            k=k,
            planner=normalized_planner,
            runtime_index=runtime_index,
            ingestion=ingestion,
        )
        plan = GenericEvidenceResolver(planner=normalized_planner).resolve(
            question,
            context_chunks,
            {},
        )
        return {
            "question": question,
            "planner": normalized_planner,
            "context_count": len(context_chunks),
            "evidence_plan": evidence_plan_to_dict(plan),
        }

    @mcp.tool()
    def gwt_collection_query(
        operation: str,
        field: str | None = None,
        value: str | None = None,
        metric: str | None = None,
        k: int = 5,
        group_field: str | None = None,
        group_a: str | None = None,
        group_b: str | None = None,
    ) -> dict[str, Any]:
        """Run exact collection operations over runtime structured memory."""
        collection = runtime_index.collection()
        normalized_operation = operation.lower().strip()
        criteria = {field: value} if field and value else {}
        if k < 1:
            return {"error": "k must be >= 1"}

        if normalized_operation == "count":
            records = collection.filter_equals(criteria) if criteria else collection.records
            return _collection_query_payload(
                operation="count",
                answer=str(len(records)),
                records=records,
                metadata={"criteria": criteria},
            )

        if normalized_operation in {"filter", "list", "find"}:
            if not criteria:
                return {"error": "filter/list/find require field and value"}
            records = collection.filter_equals(criteria)
            answer = ", ".join(record.record_id for record in records) or "none"
            return _collection_query_payload(
                operation="filter",
                answer=answer,
                records=records,
                metadata={"criteria": criteria},
            )

        if normalized_operation == "top_k":
            if metric is None:
                return {"error": "top_k requires metric"}
            records = collection.top_k(metric, k)
            answer = ", ".join(record.record_id for record in records) or "none"
            return _collection_query_payload(
                operation="top_k",
                answer=answer,
                records=records,
                metadata={"metric": metric, "k": k},
            )

        if normalized_operation == "average":
            if metric is None:
                return {"error": "average requires metric"}
            average, records = collection.average(metric, criteria)
            answer = f"{average:.1f}" if average is not None else "0.0"
            return _collection_query_payload(
                operation="average",
                answer=answer,
                records=records,
                metadata={"metric": metric, "criteria": criteria},
            )

        if normalized_operation == "compare":
            if not (group_field and group_a and group_b and metric):
                return {"error": "compare requires group_field, group_a, group_b, and metric"}
            average_a, records_a = collection.average(metric, {group_field: group_a})
            average_b, records_b = collection.average(metric, {group_field: group_b})
            if average_a is None or average_b is None:
                return {"error": "not enough numeric records to compare"}
            winner = group_a if average_a >= average_b else group_b
            return _collection_query_payload(
                operation="compare",
                answer=winner,
                records=(*records_a, *records_b),
                metadata={
                    "group_field": group_field,
                    "metric": metric,
                    "group_a": group_a,
                    "group_b": group_b,
                    "average_a": average_a,
                    "average_b": average_b,
                },
            )

        return {
            "error": f"unsupported collection operation: {operation}",
            "supported_operations": ["count", "filter", "top_k", "average", "compare"],
        }

    @mcp.tool()
    def gwt_trace_explain() -> dict[str, Any]:
        """Explain the most recent explicit attention trace."""
        if attention_trace is None or attention_trace.get_last() is None:
            return {"status": "empty", "message": "No attention trace has been recorded."}

        trace = attention_trace.get_last()
        assert trace is not None
        evidence = trace["evidence_plan"]
        phases = [step["name"] for step in trace["trace"]]
        bus_summary = _broadcast_bus_summary(trace["trace"])
        return {
            "status": "ok",
            "question": trace["question"],
            "planner": evidence["metadata"].get("planner", "unknown"),
            "strategy": evidence["strategy"],
            "answer": evidence["answer"],
            "pass_count": trace["pass_count"],
            "tool_call_count": trace["tool_call_count"],
            "phases": phases,
            "broadcast_bus": bus_summary,
            "explanation": (
                "Attention set the goal, resolved an evidence plan, admitted any required "
                "evidence, then ran broadcast passes."
            ),
            "trace": trace,
        }

    @mcp.tool()
    def gwt_bus_inspect() -> dict[str, Any]:
        """Inspect the cycle-level broadcast bus read model."""
        snapshot = cycle.inspect(target="broadcast_bus")
        return {
            "status": "ok",
            "broadcast_bus": snapshot,
            "summary": _bus_snapshot_summary(snapshot),
        }

    @mcp.tool()
    def gwt_evict(item_id: str) -> dict[str, Any]:
        """Manually remove a specific item from the workspace.

        The item returns to the preconscious buffer and can re-enter
        via competition later. Use when information is no longer relevant.

        Args:
            item_id: ID of the item to evict.
        """
        return cycle.evict_workspace_item(item_id=item_id)

    @mcp.tool()
    def gwt_link(source_id: str, target_id: str) -> dict[str, Any]:
        """Create a bidirectional link between two memory items.

        Linked items boost each other during competition via the LinkageSpecialist.
        Use this to build reasoning chains across multiple facts.

        Args:
            source_id: First item ID.
            target_id: Second item ID.
        """
        return cycle.link_items(source_id=source_id, target_id=target_id)

    @mcp.tool()
    def gwt_inspect(target: str = "workspace") -> dict[str, Any]:
        """Inspect the current state of the GWT system.

        Args:
            target: What to inspect. One of:
                - "workspace": Current workspace slot contents
                - "buffer": Top items in preconscious buffer
                - "goals": Active goals
                - "stats": System statistics
        """
        return cycle.inspect(target=target)


def _normalize_supported_planner(planner: str) -> str | None:
    normalized = planner.lower().strip() or "auto"
    if normalized in supported_planners():
        return normalized
    return None


def _restore_runtime_index(runtime_index: RuntimeMemoryIndex, ingestion: IngestionPort) -> int:
    items = ingestion.all_items()
    if not isinstance(items, list):
        return 0
    runtime_index.extend([item.content for item in items if item.content])
    return len(runtime_index.contents())


def _memory_namespace() -> dict[str, str]:
    data_dir = os.path.expanduser(os.environ.get("GWT_DATA_DIR", "~/.gwt-context"))
    parts = [part for part in data_dir.split(os.sep) if part]
    scope = "default"
    name = "default"
    if "projects" in parts:
        scope = "project"
        index = parts.index("projects")
        if index + 1 < len(parts):
            name = parts[index + 1]
    elif parts and parts[-1] == "global":
        scope = "global"
        name = "global"
    return {"scope": scope, "name": name, "data_dir": data_dir}


def _memory_tags(tags: Sequence[str] | None) -> list[str]:
    namespace = _memory_namespace()
    merged = list(tags or [])
    for tag in (f"scope:{namespace['scope']}", f"namespace:{namespace['name']}"):
        if tag not in merged:
            merged.append(tag)
    return merged


def _namespace_file_sizes(data_dir: str) -> dict[str, int]:
    root = os.path.expanduser(data_dir)
    paths = {
        "memory_db": os.path.join(root, "memory.db"),
        "vector_json": os.path.join(root, "vectors.json"),
        "vector_npy": os.path.join(root, "vectors.npy"),
        "legacy_vector_bin": os.path.join(root, "vectors.bin"),
    }
    return {
        name: os.path.getsize(path)
        for name, path in paths.items()
        if os.path.exists(path)
    }


def _import_memory_jsonl(
    *,
    jsonl: str,
    default_memory_type: MemoryType,
    tags: Sequence[str] | None,
    admit: bool,
    dedupe: bool,
    ingestion: IngestionPort,
    cycle: CyclePort,
    runtime_index: RuntimeMemoryIndex,
) -> dict[str, Any]:
    imported_ids: list[str] = []
    skipped_duplicates: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    existing_keys = _dedupe_keys(ingestion.all_items()) if dedupe else set()
    for line_number, line in enumerate(jsonl.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append({"line": line_number, "error": str(exc)})
            continue
        if not isinstance(payload, dict):
            errors.append({"line": line_number, "error": "line must decode to an object"})
            continue
        content = str(payload.get("content", "")).strip()
        if not content:
            errors.append({"line": line_number, "error": "content must not be empty"})
            continue
        source = str(payload.get("source") or "tool:gwt_import_memory")
        exported_tags = payload.get("tags", [])
        if not isinstance(exported_tags, list):
            exported_tags = []
        item_tags = _memory_tags([*exported_tags, *(tags or [])])
        key = _dedupe_key(content=content, source=source, tags=item_tags)
        if dedupe and key in existing_keys:
            skipped_duplicates.append({"line": line_number, "reason": "duplicate"})
            continue
        mt = _parse_memory_type(str(payload.get("memory_type", default_memory_type.value)))
        item = ingestion.ingest(
            content=content,
            memory_type=mt or default_memory_type,
            source=source,
            tags=item_tags,
            link_to=None,
        )
        existing_keys.add(key)
        runtime_index.add(item.content)
        imported_ids.append(item.id)
        if admit:
            cycle.enqueue_for_competition(item)

    return {
        "status": "ok" if not errors else "partial",
        "imported_count": len(imported_ids),
        "imported_ids": imported_ids,
        "skipped_duplicate_count": len(skipped_duplicates),
        "skipped_duplicates": skipped_duplicates,
        "error_count": len(errors),
        "errors": errors,
        "admit": admit,
        "dedupe": dedupe,
    }


def _dedupe_keys(items: Sequence[MemoryItem]) -> set[tuple[str, str, tuple[str, ...]]]:
    return {
        _dedupe_key(content=item.content, source=item.source, tags=item.tags)
        for item in items
    }


def _dedupe_key(
    *,
    content: str,
    source: str,
    tags: Sequence[str],
) -> tuple[str, str, tuple[str, ...]]:
    return (" ".join(content.split()), source, tuple(sorted(set(tags))))


def _working_summary_content(items: Sequence[MemoryItem]) -> str:
    lines = [
        f"Working memory compaction summary | compacted_count={len(items)}",
    ]
    for item in items[:20]:
        preview = " ".join(item.content.split())[:160]
        lines.append(f"- {item.id}: {preview}")
    if len(items) > 20:
        lines.append(f"- omitted={len(items) - 20}")
    return "\n".join(lines)


def _export_item(item: MemoryItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "content": item.content,
        "summary": item.summary,
        "memory_type": item.memory_type.value,
        "activation_state": item.activation_state.value,
        "source": item.source,
        "tags": item.tags,
        "linked_ids": item.linked_ids,
        "created_at": item.created_at.isoformat(),
        "last_accessed": item.last_accessed.isoformat(),
    }


def _parse_memory_type(memory_type: str | None) -> MemoryType | None:
    if memory_type is None:
        return None
    try:
        return MemoryType(memory_type)
    except ValueError:
        return None


def _context_chunks_for_question(
    *,
    question: str,
    k: int,
    planner: str,
    runtime_index: RuntimeMemoryIndex,
    ingestion: IngestionPort,
) -> tuple[str, ...]:
    if planner == "semantic":
        return ()
    if not runtime_index.contents():
        items = ingestion.query_similar(query=question, k=k)
        runtime_index.extend([item.content for item in items])
    return runtime_index.contents()


def _collection_query_payload(
    *,
    operation: str,
    answer: str,
    records: Sequence[StructuredRecord],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "operation": operation,
        "answer": answer,
        "matched_count": len(records),
        "matched_records": [
            {"id": record.record_id, "fields": dict(record.fields), "raw": record.raw}
            for record in records
        ],
        "supporting_evidence": [record.raw for record in records],
        "metadata": metadata,
    }


def _broadcast_bus_summary(trace_steps: Sequence[dict[str, Any]]) -> dict[str, Any]:
    proposal_count = 0
    accepted_count = 0
    inhibited_count = 0
    executed_actions: list[str] = []
    subscribers: set[str] = set()
    for step in trace_steps:
        if step.get("phase") == "broadcast_bus":
            payload = step.get("payload", {})
            proposals = payload.get("proposals", []) if isinstance(payload, dict) else []
            accepted = payload.get("accepted", []) if isinstance(payload, dict) else []
            inhibited = payload.get("inhibited", []) if isinstance(payload, dict) else []
            proposal_count += len(proposals)
            accepted_count += len(accepted)
            inhibited_count += len(inhibited)
            for proposal in accepted:
                if isinstance(proposal, dict):
                    subscribers.add(str(proposal.get("subscriber", "")))
        if step.get("phase") == "broadcast_bus_tool":
            executed_actions.append(str(step.get("name", "")))
    return {
        "proposal_count": proposal_count,
        "accepted_count": accepted_count,
        "inhibited_count": inhibited_count,
        "accepted_subscribers": sorted(subscriber for subscriber in subscribers if subscriber),
        "executed_actions": executed_actions,
        "inhibited_reasons": _trace_inhibited_reasons(trace_steps),
    }


def _bus_snapshot_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    last_result = snapshot.get("last_result")
    if not isinstance(last_result, dict):
        return {
            "configured": bool(snapshot.get("configured")),
            "proposal_count": 0,
            "accepted_count": 0,
            "inhibited_count": 0,
            "subscriber_statuses": {},
            "inhibited_reasons": {},
            "proposal_groups": {},
        }
    statuses: dict[str, int] = {}
    for report in last_result.get("subscriber_reports", []):
        if not isinstance(report, dict):
            continue
        status = str(report.get("status", "unknown"))
        statuses[status] = statuses.get(status, 0) + 1
    summary = last_result.get("summary", {})
    proposal_groups = last_result.get("proposal_groups", {})
    return {
        "configured": bool(snapshot.get("configured")),
        "proposal_count": len(last_result.get("proposals", [])),
        "accepted_count": len(last_result.get("accepted", [])),
        "inhibited_count": len(last_result.get("inhibited", [])),
        "subscriber_statuses": statuses,
        "inhibited_reasons": (
            summary.get("inhibited_reasons", {}) if isinstance(summary, dict) else {}
        ),
        "proposal_groups": proposal_groups if isinstance(proposal_groups, dict) else {},
    }


def _trace_inhibited_reasons(trace_steps: Sequence[dict[str, Any]]) -> dict[str, int]:
    reasons: dict[str, int] = {}
    for step in trace_steps:
        if step.get("phase") != "broadcast_bus":
            continue
        payload = step.get("payload", {})
        if not isinstance(payload, dict):
            continue
        for decision in payload.get("decisions", []):
            if not isinstance(decision, dict) or decision.get("status") != "inhibited":
                continue
            reason = str(decision.get("reason", "unknown"))
            reasons[reason] = reasons.get(reason, 0) + 1
    return dict(sorted(reasons.items()))
