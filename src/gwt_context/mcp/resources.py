"""MCP resource definitions for GWT-Context.

Resources provide passive read access to system state.
"""

from mcp.server.fastmcp import FastMCP

from gwt_context.application.cycle import SelectionBroadcastCycle
from gwt_context.infrastructure.storage import SQLiteMemoryStore


def register_resources(
    mcp: FastMCP,
    cycle: SelectionBroadcastCycle,
    store: SQLiteMemoryStore,
) -> None:
    """Register all GWT resources on the MCP server."""

    @mcp.resource("gwt://workspace")
    def workspace_resource() -> str:
        """Current workspace broadcast text."""
        return cycle.workspace.get_broadcast_text()

    @mcp.resource("gwt://workspace/slots")
    def workspace_slots() -> str:
        """Detailed slot-by-slot view of the workspace."""
        lines = []
        for slot in cycle.workspace.slots:
            if slot.item is not None:
                item = slot.item
                lines.append(
                    f"Slot {slot.index}: [{item.id}] "
                    f"({item.memory_type.value}, a={item.activation_level:.2f}) "
                    f"{item.content[:200]}"
                )
                if item.linked_ids:
                    lines.append(f"  Links: {', '.join(item.linked_ids)}")
            else:
                lines.append(f"Slot {slot.index}: [empty]")
        return "\n".join(lines)

    @mcp.resource("gwt://goals")
    def goals_resource() -> str:
        """Current active goals."""
        goals = cycle.goal_manager.active_goals
        if not goals:
            return "No active goals. Use gwt_set_goal to set one."
        lines = []
        for g in goals:
            lines.append(f"[{g.id}] (p={g.priority}) {g.description}")
            if g.keywords:
                lines.append(f"  Keywords: {', '.join(g.keywords)}")
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
        lines = [
            f"Total items: {store.count_items()}",
            f"Workspace: {cycle.workspace.occupied_count}/{cycle.workspace.capacity}",
            f"Buffer: {cycle.buffer.size}",
            f"Broadcasts: {store.get_broadcast_count()}",
            f"Active goals: {len(cycle.goal_manager.active_goals)}",
        ]
        return "\n".join(lines)
