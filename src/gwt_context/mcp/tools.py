"""MCP tool definitions for GWT-Context.

8 tools that form the external API surface for LLM interaction.
Each tool maps to domain/application operations.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from gwt_context.application.cycle import SelectionBroadcastCycle
from gwt_context.application.ingestion import IngestionPipeline
from gwt_context.domain.models import MemoryType


def register_tools(
    mcp: FastMCP,
    cycle: SelectionBroadcastCycle,
    ingestion: IngestionPipeline,
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

        # Push to preconscious buffer
        cycle.buffer.push(item)

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
        goal = cycle.goal_manager.set_goal(
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
        goals = cycle.goal_manager.active_goals
        candidates = cycle.buffer.top(k=20)
        result = cycle._comp.run_competition(
            candidates=candidates,
            goals=goals,
            workspace=cycle.workspace,
            n_winners=n_slots,
        )
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
    ) -> list[dict[str, Any]]:
        """Search long-term memory by semantic similarity.

        Returns matching items WITHOUT admitting them to workspace.
        Use gwt_store on relevant results to make them competition-eligible,
        or gwt_link to connect them.

        Args:
            query: Search query text.
            k: Number of results to return.
            memory_type: Optional filter (episodic/semantic/procedural/working).
        """
        mt = MemoryType(memory_type) if memory_type else None
        items = ingestion.query_similar(query=query, k=k, memory_type=mt)
        return [
            {
                "id": item.id,
                "content": item.content,
                "memory_type": item.memory_type.value,
                "activation_state": item.activation_state.value,
                "activation_level": round(item.activation_level, 3),
                "linked_ids": item.linked_ids,
                "tags": item.tags,
            }
            for item in items
        ]

    @mcp.tool()
    def gwt_evict(item_id: str) -> dict[str, Any]:
        """Manually remove a specific item from the workspace.

        The item returns to the preconscious buffer and can re-enter
        via competition later. Use when information is no longer relevant.

        Args:
            item_id: ID of the item to evict.
        """
        evicted = cycle.workspace.evict(item_id)
        if evicted is None:
            return {"status": "not_found", "message": f"Item {item_id} not in workspace"}
        cycle.buffer.push(evicted)
        return {
            "status": "evicted",
            "id": evicted.id,
            "message": "Item moved to preconscious buffer",
        }

    @mcp.tool()
    def gwt_link(source_id: str, target_id: str) -> dict[str, Any]:
        """Create a bidirectional link between two memory items.

        Linked items boost each other during competition via the LinkageSpecialist.
        Use this to build reasoning chains across multiple facts.

        Args:
            source_id: First item ID.
            target_id: Second item ID.
        """
        store = ingestion._store
        source = store.get_item(source_id)
        target = store.get_item(target_id)

        if source is None:
            return {"status": "error", "message": f"Item {source_id} not found"}
        if target is None:
            return {"status": "error", "message": f"Item {target_id} not found"}

        store.add_link(source_id, target_id)
        cycle.sync_bidirectional_link(source_id, target_id)

        return {
            "status": "linked",
            "source_id": source_id,
            "target_id": target_id,
            "message": "Bidirectional link created — items will boost each other in competition",
        }

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
        if target == "workspace":
            slots = []
            for slot in cycle.workspace.slots:
                if slot.item is not None:
                    item = slot.item
                    slots.append({
                        "slot": slot.index,
                        "id": item.id,
                        "content": item.content[:200],
                        "memory_type": item.memory_type.value,
                        "activation_level": round(item.activation_level, 3),
                        "linked_ids": item.linked_ids,
                    })
                else:
                    slots.append({"slot": slot.index, "empty": True})
            return {
                "workspace": slots,
                "occupied": cycle.workspace.occupied_count,
                "capacity": cycle.workspace.capacity,
            }

        elif target == "buffer":
            items = cycle.buffer.top(k=10)
            return {
                "buffer_size": cycle.buffer.size,
                "top_items": [
                    {
                        "id": i.id,
                        "content": i.content[:100],
                        "activation_level": round(i.activation_level, 3),
                    }
                    for i in items
                ],
            }

        elif target == "goals":
            goals = cycle.goal_manager.active_goals
            return {
                "active_goals": [
                    {
                        "id": g.id,
                        "description": g.description,
                        "priority": g.priority,
                        "keywords": g.keywords,
                    }
                    for g in goals
                ],
            }

        elif target == "stats":
            store = ingestion._store
            return {
                "total_items": store.count_items(),
                "workspace_occupied": cycle.workspace.occupied_count,
                "workspace_capacity": cycle.workspace.capacity,
                "buffer_size": cycle.buffer.size,
                "broadcasts": store.get_broadcast_count(),
                "active_goals": len(cycle.goal_manager.active_goals),
            }

        else:
            return {"error": f"Unknown target: {target}. Use: workspace, buffer, goals, stats"}
