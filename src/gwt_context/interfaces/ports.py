"""Architecture-facing port interfaces.

This module is the intended contract layer for dependency inversion.
Runtime implementations in ``src/gwt_context/infrastructure`` and
consumers in ``src/gwt_context/mcp`` and ``src/gwt_context/application``
should converge on these interfaces during P5/P6.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from gwt_context.domain.models import BroadcastRecord, Goal, MemoryItem, MemoryType


@runtime_checkable
class EmbeddingPort(Protocol):
    """Port for producing deterministic embedding vectors."""

    @property
    def dim(self) -> int:
        ...

    def embed(self, text: str) -> list[float]:
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...


@runtime_checkable
class MemoryRepositoryPort(Protocol):
    """Persistence/read operations for memory records and goals."""

    def get_item(self, item_id: str) -> MemoryItem | None:
        ...

    def get_items_by_state(self, state: Any) -> list[MemoryItem]:
        ...

    def get_all_items(self) -> list[MemoryItem]:
        ...

    def save_item(self, item: MemoryItem) -> None:
        ...

    def update_state(self, item_id: str, state: Any) -> None:
        ...

    def get_active_goals(self) -> list[Goal]:
        ...

    def save_goal(self, goal: Goal) -> None:
        ...

    def deactivate_all_goals(self) -> None:
        ...

    def deactivate_all(self) -> None:
        ...

    def save_broadcast(self, record: BroadcastRecord) -> None:
        ...

    def add_link(self, source_id: str, target_id: str) -> None:
        ...

    def get_broadcast_count(self) -> int:
        ...

    def count_items(self) -> int:
        ...


@runtime_checkable
class VectorSearchPort(Protocol):
    """Vector index adapter operations."""

    def add(self, item_id: str, embedding: list[float]) -> None:
        ...

    def remove(self, item_id: str) -> None:
        ...

    def query(self, embedding: list[float], k: int = 10) -> list[tuple[str, float]]:
        ...

    def save(self, path: Any = None) -> None:
        ...

    @property
    def count(self) -> int:
        ...


@runtime_checkable
class IngestionPort(Protocol):
    """Application service for adding and searching memory content."""

    def ingest(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.SEMANTIC,
        source: str = "",
        tags: list[str] | None = None,
        link_to: list[str] | None = None,
    ) -> MemoryItem:
        ...

    def query_similar(
        self,
        query: str,
        k: int = 10,
        memory_type: MemoryType | None = None,
    ) -> list[MemoryItem]:
        ...


@runtime_checkable
class CyclePort(Protocol):
    """Orchestration operations exposed to the MCP boundary."""

    def run(self) -> BroadcastRecord:
        ...

    def run_competition_dry(self, n_slots: int | None = None) -> Any:
        ...

    def enqueue_for_competition(self, item: MemoryItem) -> None:
        ...

    def set_goal(
        self,
        description: str,
        keywords: list[str] | None = None,
        priority: float = 1.0,
    ) -> Goal:
        ...

    def evict_workspace_item(self, item_id: str) -> dict[str, Any]:
        ...

    def link_items(self, source_id: str, target_id: str) -> dict[str, Any]:
        ...

    def inspect(self, target: str = "workspace") -> dict[str, Any]:
        ...

    @property
    def workspace(self) -> Any:
        ...

    @property
    def buffer(self) -> Any:
        ...

    @property
    def goal_manager(self) -> Any:
        ...
