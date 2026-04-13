"""Selection-Broadcast Cycle — the main GWT orchestration.

Ties together: buffer → competition → workspace admit/evict → broadcast.
This is the core "business logic" of the system.
"""

from __future__ import annotations

from gwt_context.application.goal_manager import GoalManager
from gwt_context.domain.broadcast import BroadcastAssembler
from gwt_context.domain.competition import CompetitionEngine
from gwt_context.domain.models import (
    ActivationState,
    BroadcastRecord,
    Goal,
    MemoryItem,
)
from gwt_context.domain.workspace import GlobalWorkspace
from gwt_context.infrastructure.storage import SQLiteMemoryStore
from gwt_context.infrastructure.vector_index import VectorIndex


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
        store: SQLiteMemoryStore,
        vector_index: VectorIndex,
        goal_manager: GoalManager,
    ) -> None:
        self._ws = workspace
        self._comp = competition
        self._bc = broadcast
        self._buffer = buffer
        self._store = store
        self._vi = vector_index
        self._gm = goal_manager

    @property
    def workspace(self) -> GlobalWorkspace:
        return self._ws

    @property
    def buffer(self) -> PreconsciousBuffer:
        return self._buffer

    @property
    def goal_manager(self) -> GoalManager:
        return self._gm

    def sync_bidirectional_link(self, source_id: str, target_id: str) -> None:
        """Update already-loaded session objects after persisting a new link."""
        for item in self._loaded_items(source_id):
            if target_id not in item.linked_ids:
                item.linked_ids.append(target_id)

        for item in self._loaded_items(target_id):
            if source_id not in item.linked_ids:
                item.linked_ids.append(source_id)

    def run(self) -> BroadcastRecord:
        """Execute one full selection-broadcast cycle."""
        goals = self._gm.active_goals

        # 1. Gather candidates
        candidates = self._gather_candidates(goals)

        if not candidates and not self._ws.items:
            # Nothing to compete with, return empty broadcast
            return self._bc.assemble(self._ws, goals)

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

        return record

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
