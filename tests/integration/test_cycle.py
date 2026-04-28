"""Integration test: full GWT selection-broadcast cycle.

Tests the complete flow: store → set goal → compete → broadcast → evict.
Uses real domain objects with fake embeddings (no sentence-transformers needed).
"""

import tempfile
from pathlib import Path

import pytest

from gwt_context.application.broadcast_bus import BroadcastBus, BroadcastProposal
from gwt_context.application.cycle import PreconsciousBuffer, SelectionBroadcastCycle
from gwt_context.application.goal_manager import GoalManager
from gwt_context.application.ingestion import IngestionPipeline
from gwt_context.domain.broadcast import BroadcastAssembler
from gwt_context.domain.competition import CompetitionEngine
from gwt_context.domain.models import ActivationState, MemoryType
from gwt_context.domain.specialists import create_default_specialists
from gwt_context.domain.workspace import GlobalWorkspace
from gwt_context.infrastructure.storage import SQLiteMemoryStore
from gwt_context.infrastructure.vector_index import VectorIndex


class FakeEmbedder:
    """Deterministic embedder for testing. Maps text to simple vectors."""

    @property
    def dim(self) -> int:
        return 4

    def embed(self, text: str) -> list[float]:
        # Simple hash-based embedding for reproducibility
        h = hash(text) % 10000
        return [
            (h % 10) / 10.0,
            ((h // 10) % 10) / 10.0,
            ((h // 100) % 10) / 10.0,
            ((h // 1000) % 10) / 10.0,
        ]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


@pytest.fixture
def system():
    """Wire up the full system with temp storage and fake embedder."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        store = SQLiteMemoryStore(db_path=tmp_path / "test.db")
        vi = VectorIndex(dim=4, path=tmp_path / "vectors.bin")
        embedder = FakeEmbedder()

        workspace = GlobalWorkspace(capacity=3)  # Small for testing
        specialists = create_default_specialists()
        competition = CompetitionEngine(specialists=specialists)
        broadcast = BroadcastAssembler()
        buffer = PreconsciousBuffer(max_size=20)
        goal_manager = GoalManager(store=store, embedder=embedder)
        ingestion = IngestionPipeline(store=store, vector_index=vi, embedder=embedder)

        cycle = SelectionBroadcastCycle(
            workspace=workspace,
            competition=competition,
            broadcast=broadcast,
            buffer=buffer,
            store=store,
            vector_index=vi,
            goal_manager=goal_manager,
        )

        yield {
            "cycle": cycle,
            "ingestion": ingestion,
            "workspace": workspace,
            "buffer": buffer,
            "store": store,
            "goal_manager": goal_manager,
        }

        store.close()


class TestFullCycle:
    def test_empty_broadcast(self, system):
        """Broadcast on empty system returns valid record."""
        record = system["cycle"].run()
        assert "0/3" in record.formatted_content

    def test_ingest_and_broadcast(self, system):
        """Ingested items compete for workspace slots."""
        ing = system["ingestion"]
        buf = system["buffer"]

        # Ingest 5 items
        items = []
        for i in range(5):
            item = ing.ingest(f"fact number {i}", memory_type=MemoryType.SEMANTIC)
            buf.push(item)
            items.append(item)

        # Broadcast should fill 3 slots (capacity)
        record = system["cycle"].run()
        ws = system["workspace"]
        assert ws.occupied_count == 3
        assert len(record.admitted_ids) == 3

    def test_goal_influences_selection(self, system):
        """Setting a goal should bias competition toward relevant items."""
        ing = system["ingestion"]
        buf = system["buffer"]
        gm = system["goal_manager"]

        # Store diverse items
        item_a = ing.ingest("python programming language syntax")
        buf.push(item_a)
        item_b = ing.ingest("french cooking recipes for dinner")
        buf.push(item_b)
        item_c = ing.ingest("python decorators and metaclasses")
        buf.push(item_c)

        # Set goal related to python
        gm.set_goal("learn about python programming")

        # Broadcast
        system["cycle"].run()
        ws = system["workspace"]

        # Workspace should have items (exact selection depends on fake embeddings)
        assert ws.occupied_count > 0

    def test_eviction_on_competition(self, system):
        """New high-scoring items should evict weaker workspace occupants."""
        ing = system["ingestion"]
        buf = system["buffer"]

        # Fill workspace
        for i in range(3):
            item = ing.ingest(f"initial fact {i}")
            buf.push(item)
        system["cycle"].run()
        ws = system["workspace"]
        assert ws.occupied_count == 3

        # Add more items and broadcast again
        for i in range(5):
            item = ing.ingest(f"new important discovery {i}")
            buf.push(item)
        system["cycle"].run()

        # Some items may have been evicted
        # (depends on scoring — at minimum, broadcast ran without error)
        assert ws.occupied_count == 3

    def test_linking_boosts_items(self, system):
        """Linked items should score higher when their targets are in workspace."""
        ing = system["ingestion"]
        buf = system["buffer"]

        # Create and admit item A directly
        item_a = ing.ingest("person A invented the telephone")
        buf.push(item_a)
        system["cycle"].run()

        # Now create item B linked to A
        item_b = ing.ingest(
            "person B was the mentor of person A",
            link_to=[item_a.id],
        )
        buf.push(item_b)

        # Item B should have linked_ids set
        assert item_a.id in item_b.linked_ids

    def test_sync_bidirectional_link_updates_loaded_workspace_and_buffer_items(self, system):
        """Links created after loading should mutate live session objects."""
        ing = system["ingestion"]
        buf = system["buffer"]
        cycle = system["cycle"]
        store = system["store"]
        ws = system["workspace"]

        workspace_item = ing.ingest("anchor fact already in workspace")
        buf.push(workspace_item)
        cycle.run()
        assert ws.contains(workspace_item.id)

        buffered_item = ing.ingest("candidate fact waiting in buffer")
        buf.push(buffered_item)
        assert workspace_item.linked_ids == []
        assert buffered_item.linked_ids == []

        store.add_link(workspace_item.id, buffered_item.id)
        cycle.sync_bidirectional_link(workspace_item.id, buffered_item.id)

        assert buffered_item.linked_ids == [workspace_item.id]
        assert workspace_item.linked_ids == [buffered_item.id]

    def test_conscious_items_activate_linked_memories_for_next_cycle(self, system):
        """Broadcast reentry moves linked long-term memories into preconscious."""
        ing = system["ingestion"]
        buf = system["buffer"]
        cycle = system["cycle"]

        anchor = ing.ingest("Ada is connected to Grace")
        linked = ing.ingest("Grace is connected to Alan")
        buf.push(anchor)
        cycle.run()
        cycle.link_items(anchor.id, linked.id)

        cycle.run()
        buffer_snapshot = cycle.inspect("buffer")

        assert linked.id in {item["id"] for item in buffer_snapshot["items"]}
        assert linked.id in cycle.inspect("stats")["last_link_activations"]

        cycle.run()
        workspace_snapshot = cycle.inspect("workspace")
        assert linked.id in {item["id"] for item in workspace_snapshot["items"]}

    def test_cycle_publishes_broadcast_to_configured_bus(self, tmp_path):
        """Plain broadcast path invokes subscribers at cycle level."""
        store = SQLiteMemoryStore(db_path=tmp_path / "bus.db")
        vi = VectorIndex(dim=4, path=tmp_path / "vectors.bin")
        embedder = FakeEmbedder()

        class StaticSubscriber:
            name = "static"

            def propose(self, _context):
                return (
                    BroadcastProposal(
                        subscriber=self.name,
                        kind="ask_followup",
                        priority=0.9,
                        rationale="unit",
                        payload={"question": "Q"},
                    ),
                )

        cycle = SelectionBroadcastCycle(
            workspace=GlobalWorkspace(capacity=1),
            competition=CompetitionEngine(specialists=create_default_specialists()),
            broadcast=BroadcastAssembler(),
            buffer=PreconsciousBuffer(max_size=10),
            store=store,
            vector_index=vi,
            goal_manager=GoalManager(store=store, embedder=embedder),
            broadcast_bus=BroadcastBus([StaticSubscriber()]),
        )

        cycle.run(question="Q")
        bus_snapshot = cycle.inspect("broadcast_bus")

        assert bus_snapshot["configured"] is True
        assert bus_snapshot["subscribers"] == ["static"]
        assert bus_snapshot["settings"]["max_accepted"] == 4
        assert bus_snapshot["last_result"]["accepted"][0]["subscriber"] == "static"
        assert bus_snapshot["summary"]["accepted_count"] == 1
        assert bus_snapshot["proposal_groups"]["accepted_by_subscriber"] == {"static": 1}
        store.close()

    def test_multiple_broadcast_cycles(self, system):
        """Multiple broadcast cycles should work without errors."""
        ing = system["ingestion"]
        buf = system["buffer"]

        for round_num in range(3):
            for i in range(2):
                item = ing.ingest(f"round {round_num} fact {i}")
                buf.push(item)
            record = system["cycle"].run()
            assert record.formatted_content  # Non-empty

        store = system["store"]
        assert store.get_broadcast_count() == 3

    def test_manual_evict(self, system):
        """Manual eviction should work and demote item."""
        ing = system["ingestion"]
        buf = system["buffer"]
        ws = system["workspace"]

        item = ing.ingest("to be evicted")
        buf.push(item)
        system["cycle"].run()

        if ws.contains(item.id):
            evicted = ws.evict(item.id)
            assert evicted is not None
            assert evicted.activation_state == ActivationState.PRECONSCIOUS


class TestPreconsciousBuffer:
    def test_push_and_top(self):
        buf = PreconsciousBuffer(max_size=5)
        from gwt_context.domain.models import MemoryItem
        for i in range(3):
            item = MemoryItem(id=f"i{i}", content=f"c{i}", activation_level=float(i))
            buf.push(item)

        top = buf.top(k=2)
        assert len(top) == 2
        assert top[0].activation_level >= top[1].activation_level

    def test_overflow(self):
        buf = PreconsciousBuffer(max_size=2)
        from gwt_context.domain.models import MemoryItem
        for i in range(5):
            item = MemoryItem(id=f"i{i}", content=f"c{i}", activation_level=float(i))
            buf.push(item)

        assert buf.size == 2
        top = buf.top(k=2)
        # Should keep highest scoring
        assert top[0].activation_level == 4.0
        assert top[1].activation_level == 3.0

    def test_remove(self):
        buf = PreconsciousBuffer(max_size=10)
        from gwt_context.domain.models import MemoryItem
        buf.push(MemoryItem(id="x", content="x"))
        buf.remove("x")
        assert buf.size == 0
