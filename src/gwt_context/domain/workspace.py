"""Global Workspace — the capacity-limited core of GWT.

Implements GWT markers:
  #1 Global availability — get_broadcast_text() makes all slots visible
  #4 Capacity limitation — hard slot limit
  #5 Persistence with controlled update — items stay until displaced
"""

from __future__ import annotations

from datetime import UTC, datetime

from gwt_context.domain.models import (
    ActivationState,
    BroadcastRecord,
    MemoryItem,
    WorkspaceSlot,
)


class GlobalWorkspace:
    """Capacity-limited workspace where winning memory items are broadcast.

    The workspace holds a fixed number of slots (default 7, Miller's 7±2).
    Items enter via admit() after winning competition, and leave via evict()
    when displaced by higher-scoring candidates.
    """

    DEFAULT_CAPACITY = 7

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        self._capacity = capacity
        self._slots: list[WorkspaceSlot] = [
            WorkspaceSlot(index=i) for i in range(capacity)
        ]
        self._broadcast_log: list[BroadcastRecord] = []

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def occupied_count(self) -> int:
        return sum(1 for s in self._slots if not s.is_empty)

    @property
    def free_count(self) -> int:
        return self._capacity - self.occupied_count

    @property
    def items(self) -> list[MemoryItem]:
        """All items currently in workspace."""
        return [s.item for s in self._slots if s.item is not None]

    @property
    def item_ids(self) -> set[str]:
        """IDs of all items currently in workspace."""
        return {s.item.id for s in self._slots if s.item is not None}

    @property
    def slots(self) -> list[WorkspaceSlot]:
        return list(self._slots)

    @property
    def broadcast_log(self) -> list[BroadcastRecord]:
        return list(self._broadcast_log)

    def admit(self, item: MemoryItem) -> bool:
        """Place item in first empty slot.

        Returns True if admitted, False if workspace is full.
        Caller must handle eviction before calling when full.
        """
        for slot in self._slots:
            if slot.is_empty:
                now = datetime.now(UTC)
                item.activation_state = ActivationState.CONSCIOUS
                item.entered_workspace_at = now
                item.touch()
                slot.item = item
                slot.entered_at = now
                return True
        return False

    def evict(self, item_id: str) -> MemoryItem | None:
        """Remove item by ID. Returns it with state set to PRECONSCIOUS."""
        for slot in self._slots:
            if slot.item is not None and slot.item.id == item_id:
                evicted = slot.item
                evicted.activation_state = ActivationState.PRECONSCIOUS
                evicted.entered_workspace_at = None
                slot.item = None
                slot.entered_at = None
                return evicted
        return None

    def contains(self, item_id: str) -> bool:
        return item_id in self.item_ids

    def clear(self) -> list[MemoryItem]:
        """Remove all items. Returns list of evicted items."""
        evicted = []
        for slot in self._slots:
            if slot.item is not None:
                slot.item.activation_state = ActivationState.PRECONSCIOUS
                slot.item.entered_workspace_at = None
                evicted.append(slot.item)
                slot.item = None
                slot.entered_at = None
        return evicted

    def get_broadcast_text(self) -> str:
        """Format all workspace contents for LLM context injection.

        This IS the GWT broadcast — making all workspace items
        simultaneously visible to the LLM.
        """
        if not self.items:
            return (
                f"=== GLOBAL WORKSPACE [0/{self._capacity}] ===\n"
                "Workspace empty. Use gwt_store to add information "
                "and gwt_set_goal to set your objective.\n"
                "=== END WORKSPACE ==="
            )

        lines = [f"=== GLOBAL WORKSPACE [{self.occupied_count}/{self._capacity}] ==="]
        for slot in self._slots:
            if slot.item is not None:
                item = slot.item
                lines.append(
                    f"[slot:{slot.index}|{item.memory_type.value}"
                    f"|activation={item.activation_level:.2f}] "
                    f"{item.content}"
                )
        lines.append("=== END WORKSPACE ===")
        return "\n".join(lines)

    def record_broadcast(self, record: BroadcastRecord) -> None:
        """Append a broadcast record to the log."""
        self._broadcast_log.append(record)
