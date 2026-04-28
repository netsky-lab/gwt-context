"""Workspace-impact regressions for post-broadcast subscriber proposals."""

from pathlib import Path

from gwt_context.application.attention import AttentionController, GenericEvidenceResolver
from gwt_context.application.broadcast_bus import BroadcastBus, BroadcastContext, BroadcastProposal
from gwt_context.application.cycle import PreconsciousBuffer, SelectionBroadcastCycle
from gwt_context.application.goal_manager import GoalManager
from gwt_context.application.ingestion import IngestionPipeline
from gwt_context.domain.broadcast import BroadcastAssembler
from gwt_context.domain.competition import CompetitionEngine
from gwt_context.domain.models import MemoryItem, MemoryType
from gwt_context.domain.specialists import create_default_specialists
from gwt_context.domain.workspace import GlobalWorkspace
from gwt_context.infrastructure.storage import SQLiteMemoryStore
from gwt_context.infrastructure.vector_index import VectorIndex


class FakeEmbedder:
    @property
    def dim(self) -> int:
        return 4

    def embed(self, text: str) -> list[float]:
        value = sum(ord(char) for char in text)
        return [
            (value % 10) / 10.0,
            ((value // 10) % 10) / 10.0,
            ((value // 100) % 10) / 10.0,
            ((value // 1000) % 10) / 10.0,
        ]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class QuerySubscriber:
    name = "query"

    def propose(self, _context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
        return (
            BroadcastProposal(
                subscriber=self.name,
                kind="query_memory",
                priority=0.9,
                rationale="Continue the relation exposed by the broadcast.",
                payload={"query": "Paper Beta cites"},
            ),
        )


class RoutedIngestion:
    def __init__(
        self,
        real_ingestion: IngestionPipeline,
        anchor: MemoryItem,
        followup: MemoryItem,
    ) -> None:
        self._real = real_ingestion
        self._anchor = anchor
        self._followup = followup

    def ingest(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.SEMANTIC,
        source: str = "",
        tags: list[str] | None = None,
        link_to: list[str] | None = None,
    ) -> MemoryItem:
        return self._real.ingest(content, memory_type, source, tags, link_to)

    def query_similar(
        self,
        query: str,
        k: int = 10,
        memory_type: MemoryType | None = None,
    ) -> list[MemoryItem]:
        if query == "Paper Beta cites":
            return [self._followup]
        return [self._anchor]

    def all_items(self) -> list[MemoryItem]:
        return self._real.all_items()


def test_subscriber_query_changes_workspace_on_following_attention_pass(tmp_path: Path) -> None:
    store = SQLiteMemoryStore(db_path=tmp_path / "attention-bus.db")
    vector_index = VectorIndex(dim=4, path=tmp_path / "vectors.bin")
    embedder = FakeEmbedder()
    real_ingestion = IngestionPipeline(store=store, vector_index=vector_index, embedder=embedder)
    workspace = GlobalWorkspace(capacity=2)
    cycle = SelectionBroadcastCycle(
        workspace=workspace,
        competition=CompetitionEngine(specialists=create_default_specialists()),
        broadcast=BroadcastAssembler(),
        buffer=PreconsciousBuffer(max_size=10),
        store=store,
        vector_index=vector_index,
        goal_manager=GoalManager(store=store, embedder=embedder),
    )
    anchor = real_ingestion.ingest("Paper Alpha -> cites -> Paper Beta")
    followup = real_ingestion.ingest("Paper Beta -> cites -> Paper Gamma")
    ingestion = RoutedIngestion(real_ingestion, anchor, followup)

    result = AttentionController(
        cycle=cycle,
        ingestion=ingestion,
        resolvers=[GenericEvidenceResolver(planner="semantic")],
        broadcast_bus=BroadcastBus([QuerySubscriber()]),
    ).run("What does Paper Alpha cite cite?", passes=2)

    workspace_ids = {
        item["id"] for item in cycle.inspect("workspace")["items"] if item["id"]
    }
    assert anchor.id in workspace_ids
    assert followup.id in workspace_ids
    assert "subscriber_query" in [step.name for step in result.steps]
    assert followup.id in result.admitted_ids
    store.close()
