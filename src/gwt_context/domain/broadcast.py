"""Broadcast assembler — formats workspace for global availability.

Implements GWT marker #1: the broadcast makes all workspace contents
simultaneously visible to the LLM in a structured format.
"""

from __future__ import annotations

from gwt_context.domain.models import BroadcastRecord, Goal, MemoryItem
from gwt_context.domain.workspace import GlobalWorkspace


class BroadcastAssembler:
    """Formats workspace contents into broadcast text.

    The broadcast is the key GWT mechanism: it takes whatever is in
    the workspace and makes it globally available. The format is
    designed for LLM consumption — structured, scannable, with
    metadata that helps the LLM understand activation levels.
    """

    def __init__(self, max_tokens: int = 4000) -> None:
        self._max_tokens = max_tokens

    def assemble(
        self,
        workspace: GlobalWorkspace,
        goals: list[Goal],
        evicted: list[MemoryItem] | None = None,
        admitted: list[MemoryItem] | None = None,
    ) -> BroadcastRecord:
        """Create a broadcast record from current workspace state.

        Args:
            workspace: The global workspace to broadcast.
            goals: Active goals (shown in broadcast header).
            evicted: Items that were just evicted (for the record).
            admitted: Items that were just admitted (for the record).
        """
        evicted = evicted or []
        admitted = admitted or []

        sections: list[str] = []

        # Goal context
        active_goals = [g for g in goals if g.active]
        if active_goals:
            goal_text = "; ".join(g.description for g in active_goals)
            sections.append(f"[GOALS: {goal_text}]")
        else:
            sections.append("[GOALS: none set]")

        sections.append("")

        # Workspace contents
        cap = workspace.capacity
        occ = workspace.occupied_count
        sections.append(f"=== GLOBAL WORKSPACE [{occ}/{cap}] ===")

        token_budget = self._max_tokens
        # Reserve ~100 tokens for header/footer/transitions
        token_budget -= 100

        for slot in workspace.slots:
            if slot.item is not None:
                item = slot.item
                content = item.content
                item_tokens = len(content) // 4
                if item_tokens > token_budget:
                    # Truncate to fit budget, prefer summary if available
                    if item.summary:
                        content = item.summary
                    else:
                        max_chars = token_budget * 4
                        content = content[:max_chars] + "...[truncated]"
                token_budget -= len(content) // 4
                sections.append(
                    f"[slot:{slot.index}|{item.memory_type.value}"
                    f"|a={item.activation_level:.2f}] "
                    f"{content}"
                )

        sections.append("=== END WORKSPACE ===")

        # Transition summary (what changed)
        if evicted or admitted:
            sections.append("")
            if admitted:
                ids = ", ".join(i.id for i in admitted)
                sections.append(f"[ADMITTED: {ids}]")
            if evicted:
                ids = ", ".join(i.id for i in evicted)
                sections.append(f"[EVICTED: {ids}]")

        formatted = "\n".join(sections)

        return BroadcastRecord(
            workspace_snapshot=[i.id for i in workspace.items],
            goal_id=active_goals[0].id if active_goals else None,
            formatted_content=formatted,
            evicted_ids=[i.id for i in evicted],
            admitted_ids=[i.id for i in admitted],
        )
