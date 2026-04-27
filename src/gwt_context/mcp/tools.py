"""MCP tool definitions for GWT-Context.

9 tools that form the external API surface for LLM interaction.
Each tool maps to domain/application operations.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from gwt_context.application.attention import (
    AttentionController,
    GenericEvidenceResolver,
    evidence_plan_to_dict,
)
from gwt_context.domain.models import MemoryType
from gwt_context.interfaces.ports import CyclePort, IngestionPort


def register_tools(
    mcp: FastMCP,
    cycle: CyclePort,
    ingestion: IngestionPort,
) -> None:
    """Register all GWT tools on the MCP server."""

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
        try:
            mt = MemoryType(memory_type)
        except ValueError:
            mt = MemoryType.SEMANTIC

        item = ingestion.ingest(
            content=content,
            memory_type=mt,
            source="tool:gwt_store",
            tags=tags,
            link_to=link_to,
        )

        cycle.enqueue_for_competition(item)

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
    ) -> list[dict[str, Any]]:
        """Search long-term memory by semantic similarity.

        By default this returns matching items without admitting them to workspace.
        Set admit=true when the results should compete for the next broadcast.

        Args:
            query: Search query text.
            k: Number of results to return.
            memory_type: Optional filter (episodic/semantic/procedural/working).
            admit: Whether to enqueue matching items for workspace competition.
        """
        mt = MemoryType(memory_type) if memory_type else None
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
    ) -> dict[str, Any]:
        """Run an explicit attention pass for the current question.

        This is a one-call path for goal-directed GWT selection:
        set the active goal, plan semantic evidence queries, admit matches into
        competition, run broadcast, and return the selected workspace.

        Args:
            question: Current task/question that should guide attention.
            keywords: Optional goal keywords. If omitted, keywords are inferred.
            k: Number of semantic matches to admit per planned query.
        """
        controller = AttentionController(
            cycle=cycle,
            ingestion=ingestion,
            resolvers=[GenericEvidenceResolver()],
            query_k=k,
            admit_query_results=True,
        )
        run = controller.run(question=question, keywords=keywords)
        return {
            "question": question,
            "evidence_plan": evidence_plan_to_dict(run.evidence),
            "tool_call_count": run.tool_call_count,
            "admitted_ids": list(run.admitted_ids),
            "broadcast": run.broadcast_text,
            "workspace": cycle.inspect("workspace"),
            "trace": [
                {
                    "phase": step.phase,
                    "name": step.name,
                    "payload": dict(step.payload),
                }
                for step in run.steps
            ],
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
