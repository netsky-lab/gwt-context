"""MCP tool definitions for GWT-Context.

12 tools that form the external API surface for LLM interaction.
Each tool maps to domain/application operations.
"""

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
from gwt_context.domain.models import MemoryType
from gwt_context.interfaces.ports import CyclePort, IngestionPort


def register_tools(
    mcp: FastMCP,
    cycle: CyclePort,
    ingestion: IngestionPort,
    attention_trace: AttentionTraceStore | None = None,
) -> None:
    """Register all GWT tools on the MCP server."""
    runtime_index = RuntimeMemoryIndex()

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
            tags=tags,
            link_to=link_to,
        )

        cycle.enqueue_for_competition(item)
        runtime_index.add(item.content or content)

        return {
            "id": item.id,
            "memory_type": item.memory_type.value,
            "activation_state": item.activation_state.value,
            "linked_to": item.linked_ids,
            "status": "stored and ready for competition",
        }

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
    }
