"""Content ingestion pipeline — transforms raw content into MemoryItems."""

from __future__ import annotations

from gwt_context.domain.models import ActivationState, MemoryItem, MemoryType
from gwt_context.interfaces.ports import EmbeddingPort, MemoryRepositoryPort, VectorSearchPort


class IngestionPipeline:
    """Processes raw content into embedded, indexed MemoryItems.

    Flow: content → MemoryItem → embed → store in SQLite → index in hnswlib.
    """

    def __init__(
        self,
        store: MemoryRepositoryPort,
        vector_index: VectorSearchPort,
        embedder: EmbeddingPort,
    ) -> None:
        self._store = store
        self._vi = vector_index
        self._embedder = embedder

    def ingest(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.SEMANTIC,
        source: str = "",
        tags: list[str] | None = None,
        link_to: list[str] | None = None,
    ) -> MemoryItem:
        """Ingest content into the system.

        Creates a MemoryItem, embeds it, stores in SQLite and vector index.
        State is set to PRECONSCIOUS (ready for competition).

        Args:
            content: Text to store.
            memory_type: Classification.
            source: Where this came from.
            tags: Optional tags.
            link_to: Optional list of item IDs to link to.

        Returns:
            The created MemoryItem.
        """
        item = MemoryItem(
            content=content,
            memory_type=memory_type,
            activation_state=ActivationState.PRECONSCIOUS,
            source=source,
            tags=tags or [],
        )

        # Embed
        item.embedding = self._embedder.embed(content)

        # Store
        self._store.save_item(item)
        self._vi.add(item.id, item.embedding)
        self._vi.save()

        # Create links
        if link_to:
            for target_id in link_to:
                if self._store.get_item(target_id) is not None:
                    self._store.add_link(item.id, target_id)
                    item.linked_ids.append(target_id)

        return item

    def query_similar(
        self,
        query: str,
        k: int = 10,
        memory_type: MemoryType | None = None,
    ) -> list[MemoryItem]:
        """Search for semantically similar items.

        Args:
            query: Search text.
            k: Number of results.
            memory_type: Optional type filter.

        Returns:
            List of MemoryItems sorted by similarity.
        """
        query_embedding = self._embedder.embed(query)
        results = self._vi.query(query_embedding, k=k * 2)  # Over-fetch for filtering

        items = []
        for item_id, _similarity in results:
            item = self._store.get_item(item_id)
            if item is None:
                continue
            if memory_type and item.memory_type != memory_type:
                continue
            items.append(item)
            if len(items) >= k:
                break

        return items
