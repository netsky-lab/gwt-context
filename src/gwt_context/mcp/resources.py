"""MCP resource definitions for GWT-Context.

Resources provide passive read access to system state.
"""

import json

from mcp.server.fastmcp import FastMCP

from gwt_context.application.attention import AttentionTraceStore
from gwt_context.interfaces.ports import CyclePort, MemoryRepositoryPort


def register_resources(
    mcp: FastMCP,
    cycle: CyclePort,
    store: MemoryRepositoryPort,
    attention_trace: AttentionTraceStore | None = None,
) -> None:
    """Register all GWT resources on the MCP server."""

    @mcp.resource("gwt://workspace")
    def workspace_resource() -> str:
        """Current workspace broadcast text."""
        return cycle.get_workspace_broadcast()

    @mcp.resource("gwt://workspace/slots")
    def workspace_slots() -> str:
        """Detailed slot-by-slot view of the workspace."""
        lines = []
        snapshot = cycle.inspect("workspace")
        for item in snapshot.get("items", []):
            if not item.get("empty"):
                lines.append(
                    f"Slot {item['index']}: [{item['id']}] "
                    f"({item['memory_type']}, a={item['activation_level']:.2f}) "
                    f"{item['content'][:200]}"
                )
                if item.get("linked_ids"):
                    lines.append(f"  Links: {', '.join(item['linked_ids'])}")
            else:
                lines.append(f"Slot {item['index']}: [empty]")
        return "\n".join(lines)

    @mcp.resource("gwt://goals")
    def goals_resource() -> str:
        """Current active goals."""
        goals = cycle.inspect("goals").get("items", [])
        if not goals:
            return "No active goals. Use gwt_set_goal to set one."
        lines = []
        for goal in goals:
            lines.append(f"[{goal['id']}] (p={goal['priority']}) {goal['description']}")
            if goal.get("keywords"):
                lines.append(f"Keywords: {', '.join(goal['keywords'])}")
        return "\n".join(lines)

    @mcp.resource("gwt://memory/{item_id}")
    def memory_item_resource(item_id: str) -> str:
        """Full details of a specific memory item."""
        item = store.get_item(item_id)
        if item is None:
            return f"Item {item_id} not found."
        lines = [
            f"ID: {item.id}",
            f"Type: {item.memory_type.value}",
            f"State: {item.activation_state.value}",
            f"Activation: {item.activation_level:.3f}",
            f"Access count: {item.access_count}",
            f"Created: {item.created_at.isoformat()}",
            f"Last accessed: {item.last_accessed.isoformat()}",
            f"Tags: {', '.join(item.tags) if item.tags else 'none'}",
            f"Links: {', '.join(item.linked_ids) if item.linked_ids else 'none'}",
            f"Content: {item.content}",
        ]
        return "\n".join(lines)

    @mcp.resource("gwt://stats")
    def stats_resource() -> str:
        """System statistics."""
        workspace = cycle.inspect("workspace")
        stats = cycle.inspect("stats")
        lines = [
            f"Total items: {stats['total_items']}",
            f"Workspace: {workspace['occupied_count']}/{workspace['capacity']}",
            f"Buffer: {stats['buffer_size']}",
            f"Broadcasts: {stats['broadcasts']}",
            f"Active goals: {stats['active_goals']}",
        ]
        return "\n".join(lines)

    @mcp.resource("gwt://health")
    def health_resource() -> str:
        """Compact runtime health summary."""
        workspace = cycle.inspect("workspace")
        stats = cycle.inspect("stats")
        bus = cycle.inspect("broadcast_bus")
        items = store.get_all_items()
        bus_configured = bool(bus.get("configured")) if isinstance(bus, dict) else False
        checks = {
            "workspace_readable": isinstance(workspace, dict),
            "stats_readable": isinstance(stats, dict),
            "broadcast_bus_configured": bus_configured,
            "persistent_store_readable": isinstance(items, list),
        }
        return json.dumps(
            {
                "status": "ready" if all(checks.values()) else "degraded",
                "checks": checks,
                "counts": {
                    "persisted_items": len(items),
                    "workspace_occupied": workspace.get("occupied_count", 0),
                    "workspace_capacity": workspace.get("capacity", 0),
                    "buffer_size": stats.get("buffer_size", 0),
                    "broadcasts": stats.get("broadcasts", 0),
                    "active_goals": stats.get("active_goals", 0),
                },
            },
            indent=2,
            sort_keys=True,
        )

    @mcp.resource("gwt://attention/last")
    def last_attention_resource() -> str:
        """Most recent gwt_attend trace."""
        if attention_trace is None or attention_trace.get_last() is None:
            return "No attention run recorded. Use gwt_attend first."
        return json.dumps(attention_trace.get_last(), indent=2)
