"""Selection-Broadcast Cycle — the main GWT orchestration.

Ties together: buffer → competition → workspace admit/evict → broadcast.
This is the core "business logic" of the system.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from gwt_context.application.broadcast_bus import (
    BroadcastBus,
    BroadcastBusResult,
    BroadcastContext,
    broadcast_bus_result_groups,
    broadcast_bus_result_summary,
    broadcast_bus_result_to_dict,
)
from gwt_context.domain.broadcast import BroadcastAssembler
from gwt_context.domain.competition import CompetitionEngine
from gwt_context.domain.models import (
    ActivationState,
    BroadcastRecord,
    CompetitionResult,
    Goal,
    MemoryItem,
)
from gwt_context.domain.workspace import GlobalWorkspace
from gwt_context.interfaces.ports import GoalManagerPort, MemoryRepositoryPort, VectorSearchPort


class PreconsciousBuffer:
    """Ranked queue of memory candidates ready to enter workspace.

    Sorted by activation_level descending. Items here have been
    recently ingested or evicted from workspace — they're "on deck".
    """

    def __init__(self, max_size: int = 50) -> None:
        self._max = max_size
        self._items: dict[str, MemoryItem] = {}

    @property
    def size(self) -> int:
        return len(self._items)

    def push(self, item: MemoryItem) -> None:
        """Add item to buffer. Overflow drops lowest-scoring items."""
        item.activation_state = ActivationState.PRECONSCIOUS
        self._items[item.id] = item
        self._enforce_limit()

    def push_many(self, items: list[MemoryItem]) -> None:
        for item in items:
            item.activation_state = ActivationState.PRECONSCIOUS
            self._items[item.id] = item
        self._enforce_limit()

    def remove(self, item_id: str) -> None:
        self._items.pop(item_id, None)

    def top(self, k: int = 20) -> list[MemoryItem]:
        """Get top-k items sorted by activation level."""
        sorted_items = sorted(
            self._items.values(),
            key=lambda i: i.activation_level,
            reverse=True,
        )
        return sorted_items[:k]

    def all_items(self) -> list[MemoryItem]:
        return list(self._items.values())

    def _enforce_limit(self) -> None:
        if len(self._items) <= self._max:
            return
        sorted_items = sorted(
            self._items.values(),
            key=lambda i: i.activation_level,
            reverse=True,
        )
        keep = {item.id for item in sorted_items[:self._max]}
        for item_id in list(self._items):
            if item_id not in keep:
                overflow = self._items.pop(item_id)
                overflow.activation_state = ActivationState.LONG_TERM


class SelectionBroadcastCycle:
    """Orchestrates the full GWT selection-broadcast cycle.

    Steps:
    1. Gather candidates from buffer + vector search (by goal)
    2. Run all specialists to score candidates (competition)
    3. Winners enter workspace, losers evicted
    4. Broadcast assembled and returned

    This is what gwt_broadcast() calls.
    """

    def __init__(
        self,
        workspace: GlobalWorkspace,
        competition: CompetitionEngine,
        broadcast: BroadcastAssembler,
        buffer: PreconsciousBuffer,
        store: MemoryRepositoryPort,
        vector_index: VectorSearchPort,
        goal_manager: GoalManagerPort,
        broadcast_bus: BroadcastBus | None = None,
    ) -> None:
        self._ws = workspace
        self._comp = competition
        self._bc = broadcast
        self._buffer = buffer
        self._store = store
        self._vi = vector_index
        self._gm = goal_manager
        self._broadcast_bus = broadcast_bus
        self._last_broadcast_bus_result: BroadcastBusResult | None = None
        self._last_link_activations: tuple[str, ...] = ()

    @property
    def workspace(self) -> GlobalWorkspace:
        return self._ws

    @property
    def buffer(self) -> PreconsciousBuffer:
        return self._buffer

    @property
    def goal_manager(self) -> GoalManagerPort:
        return self._gm

    def run_competition_dry(self, n_slots: int | None = None) -> CompetitionResult:
        """Dry-run competition without mutating workspace state."""
        goals = self._gm.active_goals
        candidates = self._gather_candidates(goals)
        return self._comp.run_competition(
            candidates=candidates,
            goals=goals,
            workspace=self._ws,
            n_winners=n_slots,
        )

    def get_workspace_broadcast(self) -> str:
        """Return the current workspace broadcast text without running a cycle."""
        return self._ws.get_broadcast_text()

    def get_last_broadcast_bus_result(self) -> BroadcastBusResult | None:
        """Return the most recent broadcast-bus result, if configured."""
        return self._last_broadcast_bus_result

    def enqueue_for_competition(self, item: MemoryItem) -> None:
        """Add an item to the preconscious buffer for the next cycle."""
        self._buffer.push(item)
        self._store.update_state(item.id, ActivationState.PRECONSCIOUS)

    def set_goal(
        self,
        description: str,
        keywords: list[str] | None = None,
        priority: float = 1.0,
    ) -> Goal:
        """Set current competition objective."""
        return self._gm.set_goal(description=description, keywords=keywords, priority=priority)

    def evict_workspace_item(self, item_id: str) -> dict[str, object]:
        """Evict a workspace item and move it to preconscious state."""
        evicted = self._ws.evict(item_id)
        if evicted is None:
            return {
                "status": "not_found",
                "id": item_id,
                "message": "Item is not currently in workspace.",
            }
        self._buffer.push(evicted)
        self._store.update_state(item_id, ActivationState.PRECONSCIOUS)
        return {
            "status": "evicted",
            "id": item_id,
            "state": evicted.activation_state.value,
            "message": "Item moved to preconscious buffer.",
        }

    def link_items(self, source_id: str, target_id: str) -> dict[str, object]:
        """Create/refresh bidirectional links between items."""
        self._store.add_link(source_id, target_id)
        self.sync_bidirectional_link(source_id, target_id)
        return {
            "status": "linked",
            "source_id": source_id,
            "target_id": target_id,
        }

    def inspect(self, target: str = "workspace") -> dict[str, object]:
        """Read model snapshot for MCP observability."""
        normalized = target.lower().strip()
        if normalized == "workspace":
            return {
                "target": "workspace",
                "occupied_count": self._ws.occupied_count,
                "capacity": self._ws.capacity,
                "items": [
                    {
                        "index": slot.index,
                        "id": slot.item.id if slot.item else None,
                        "content": slot.item.content if slot.item else "",
                        "memory_type": slot.item.memory_type.value if slot.item else "",
                        "activation_level": slot.item.activation_level if slot.item else 0.0,
                        "linked_ids": slot.item.linked_ids if slot.item else [],
                        "empty": slot.is_empty,
                    }
                    for slot in self._ws.slots
                ],
            }
        if normalized == "buffer":
            items = self._buffer.all_items()
            return {
                "target": "buffer",
                "size": len(items),
                "items": [
                    {
                        "id": item.id,
                        "content": item.content,
                        "memory_type": item.memory_type.value,
                        "activation_level": item.activation_level,
                    }
                    for item in items
                ],
            }
        if normalized == "goals":
            return {
                "target": "goals",
                "count": len(self._gm.active_goals),
                "items": [
                    {
                        "id": goal.id,
                        "description": goal.description,
                        "keywords": goal.keywords,
                        "priority": goal.priority,
                    }
                    for goal in self._gm.active_goals
                ],
            }
        if normalized == "stats":
            return {
                "target": "stats",
                "total_items": self._store.count_items(),
                "broadcasts": self._store.get_broadcast_count(),
                "buffer_size": self._buffer.size,
                "workspace_count": self._ws.occupied_count,
                "active_goals": len(self._gm.active_goals),
                "last_link_activations": list(self._last_link_activations),
            }
        if normalized == "broadcast_bus":
            bus_summary = (
                broadcast_bus_result_summary(self._last_broadcast_bus_result)
                if self._last_broadcast_bus_result is not None
                else None
            )
            proposal_groups = (
                broadcast_bus_result_groups(self._last_broadcast_bus_result)
                if self._last_broadcast_bus_result is not None
                else None
            )
            return {
                "target": "broadcast_bus",
                "configured": self._broadcast_bus is not None,
                "subscribers": (
                    [subscriber.name for subscriber in self._broadcast_bus.subscribers]
                    if self._broadcast_bus is not None
                    else []
                ),
                "settings": (
                    self._broadcast_bus.settings
                    if self._broadcast_bus is not None
                    else {}
                ),
                "last_result": (
                    broadcast_bus_result_to_dict(self._last_broadcast_bus_result)
                    if self._last_broadcast_bus_result is not None
                    else None
                ),
                "summary": bus_summary,
                "proposal_groups": proposal_groups,
                "last_link_activations": list(self._last_link_activations),
            }

        return {"target": normalized, "status": "unknown", "error": "Unknown target"}

    def sync_bidirectional_link(self, source_id: str, target_id: str) -> None:
        """Update already-loaded session objects after persisting a new link."""
        for item in self._loaded_items(source_id):
            if target_id not in item.linked_ids:
                item.linked_ids.append(target_id)

        for item in self._loaded_items(target_id):
            if source_id not in item.linked_ids:
                item.linked_ids.append(source_id)

    def run(
        self,
        *,
        question: str | None = None,
        evidence_plan: Any = None,
        context_chunks: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
        pass_number: int = 1,
    ) -> BroadcastRecord:
        """Execute one full selection-broadcast cycle."""
        goals = self._gm.active_goals

        # 1. Gather candidates
        candidates = self._gather_candidates(goals)

        if not candidates and not self._ws.items:
            # Nothing to compete with, return empty broadcast
            record = self._bc.assemble(self._ws, goals)
            self._ws.record_broadcast(record)
            self._store.save_broadcast(record)
            self._last_link_activations = ()
            self._publish_broadcast_bus(
                record=record,
                question=question,
                evidence_plan=evidence_plan,
                context_chunks=context_chunks,
                metadata=metadata,
                pass_number=pass_number,
            )
            return record

        # 2. Run competition
        result = self._comp.run_competition(
            candidates=candidates,
            goals=goals,
            workspace=self._ws,
        )

        # 3. Apply evictions
        for evicted in result.evicted:
            self._ws.evict(evicted.id)
            self._buffer.push(evicted)
            self._store.update_state(evicted.id, ActivationState.PRECONSCIOUS)

        # 4. Admit winners
        for winner in result.winners:
            self._ws.admit(winner)
            self._buffer.remove(winner.id)
            self._store.update_state(winner.id, ActivationState.CONSCIOUS)

        # 5. Assemble broadcast
        record = self._bc.assemble(
            self._ws, goals,
            evicted=result.evicted,
            admitted=result.winners,
        )
        self._ws.record_broadcast(record)
        self._store.save_broadcast(record)
        self._last_link_activations = tuple(self._activate_workspace_links())
        self._publish_broadcast_bus(
            record=record,
            question=question,
            evidence_plan=evidence_plan,
            context_chunks=context_chunks,
            metadata=metadata,
            pass_number=pass_number,
        )

        return record

    def _publish_broadcast_bus(
        self,
        *,
        record: BroadcastRecord,
        question: str | None,
        evidence_plan: Any,
        context_chunks: Sequence[str],
        metadata: Mapping[str, Any] | None,
        pass_number: int,
    ) -> None:
        if self._broadcast_bus is None:
            self._last_broadcast_bus_result = None
            return
        active_goal = self._gm.active_goals[0].description if self._gm.active_goals else ""
        bus_question = question or active_goal
        chunks = tuple(context_chunks) or tuple(item.content for item in self._ws.items)
        self._last_broadcast_bus_result = self._broadcast_bus.publish(
            BroadcastContext(
                question=bus_question,
                broadcast_id=str(record.id),
                broadcast_text=record.formatted_content,
                pass_number=pass_number,
                evidence_plan=evidence_plan,
                context_chunks=chunks,
                metadata=metadata or {},
            )
        )

    def _activate_workspace_links(self) -> list[str]:
        """Move linked long-term memories into preconscious state for the next cycle."""
        activated: list[str] = []
        seen_ids = {item.id for item in self._ws.items}
        seen_ids.update(item.id for item in self._buffer.all_items())
        for item in self._ws.items:
            for linked_id in item.linked_ids:
                if linked_id in seen_ids:
                    continue
                linked = self._store.get_item(linked_id)
                if linked is None:
                    continue
                self._buffer.push(linked)
                self._store.update_state(linked.id, ActivationState.PRECONSCIOUS)
                activated.append(linked.id)
                seen_ids.add(linked.id)
        return activated

    def _gather_candidates(self, goals: list[Goal]) -> list[MemoryItem]:
        """Collect candidates from buffer and vector search."""
        # Buffer candidates
        buffer_items = self._buffer.top(k=20)
        seen_ids = {item.id for item in buffer_items}

        # Vector search by goal (if goals exist)
        if goals:
            for goal in goals:
                if goal.embedding is None:
                    continue
                results = self._vi.query(goal.embedding, k=10)
                for item_id, _sim in results:
                    if item_id in seen_ids or self._ws.contains(item_id):
                        continue
                    item = self._store.get_item(item_id)
                    if item is not None:
                        buffer_items.append(item)
                        seen_ids.add(item_id)

        return buffer_items

    def _loaded_items(self, item_id: str) -> list[MemoryItem]:
        """Return all live in-session objects for the requested item ID."""
        loaded: list[MemoryItem] = []
        seen_refs: set[int] = set()

        for item in self._ws.items + self._buffer.all_items():
            if item.id != item_id:
                continue
            item_ref = id(item)
            if item_ref in seen_refs:
                continue
            loaded.append(item)
            seen_refs.add(item_ref)

        return loaded
