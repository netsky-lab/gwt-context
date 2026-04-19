"""Port-level wiring and construction regressions for application services."""

from types import SimpleNamespace
from unittest.mock import Mock

from gwt_context.application.cycle import PreconsciousBuffer, SelectionBroadcastCycle
from gwt_context.application.goal_manager import GoalManager
from gwt_context.application.ingestion import IngestionPipeline
from gwt_context.domain.broadcast import BroadcastAssembler
from gwt_context.domain.competition import CompetitionEngine
from gwt_context.domain.models import ActivationState, Goal, MemoryItem, MemoryType
from gwt_context.domain.specialists import create_default_specialists
from gwt_context.domain.workspace import GlobalWorkspace
from gwt_context.infrastructure.config import GWTConfig
from gwt_context.infrastructure.storage import SQLiteMemoryStore
from gwt_context.infrastructure.vector_index import VectorIndex
from gwt_context.server import create_server


class RecordingEmbedder:
    """Deterministic embedder with call recording for protocol-based tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    @property
    def dim(self) -> int:
        return 4

    def embed(self, text: str) -> list[float]:
        self.calls.append((text,))
        return [float(len(text)), 0.0, 0.0, 0.0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


def test_goal_manager_uses_ports_for_goal_lifecycle() -> None:
    store = Mock()
    store.get_active_goals = Mock(return_value=[])
    store.deactivate_all_goals = Mock()
    store.save_goal = Mock()

    embedder = RecordingEmbedder()
    manager = GoalManager(store=store, embedder=embedder)

    goal = manager.set_goal("collect apples", keywords=["fruit"], priority=1.2)

    store.deactivate_all_goals.assert_called_once_with()
    store.save_goal.assert_called_once_with(goal)
    assert goal.description == "collect apples"
    assert goal.keywords == ["fruit"]
    assert goal.priority == 1.2
    assert embedder.calls == [("collect apples",)]


def test_ingestion_pipeline_uses_ports_for_store_and_index() -> None:
    store = Mock()
    store.get_item = Mock(return_value=None)
    store.save_item = Mock()

    index = Mock()
    index.add = Mock()
    index.save = Mock()
    index.query = Mock(return_value=[("link-target", 0.98), ("other", 0.4)])

    embedder = RecordingEmbedder()
    pipeline = IngestionPipeline(store=store, vector_index=index, embedder=embedder)

    item = pipeline.ingest(
        "apples grow on trees",
        memory_type=MemoryType.SEMANTIC,
        source="unit",
        tags=["botany"],
        link_to=["link-target"],
    )
    similar = pipeline.query_similar("apples", k=2)

    assert item.activation_state == ActivationState.PRECONSCIOUS
    assert item.content == "apples grow on trees"
    store.save_item.assert_called_once_with(item)
    index.add.assert_called_once()
    index.save.assert_called_once()
    assert similar == []
    assert any(call.args[0] == "link-target" for call in store.get_item.call_args_list)


def test_cycle_is_constructed_from_port_dependencies() -> None:
    store = Mock()
    store.get_item = Mock(side_effect=lambda item_id: MemoryItem(id=item_id, content=item_id))
    store.update_state = Mock()
    store.count_items = Mock(return_value=0)
    store.get_broadcast_count = Mock(return_value=0)

    index = Mock()
    index.query = Mock(return_value=[("goal-item", 0.9)])

    buffer = PreconsciousBuffer(max_size=10)
    workspace = GlobalWorkspace(capacity=2)
    specialists = create_default_specialists()
    competition = CompetitionEngine(specialists=specialists)
    broadcast = BroadcastAssembler()

    goal = Goal(description="fruit", keywords=["fruit"], priority=1.0)
    goal.embedding = [0.1, 0.0, 0.0, 0.0]
    goal_manager = Mock()
    goal_manager.active_goals = [goal]

    competition_result = SimpleNamespace(
        winners=[],
        evicted=[],
    )
    competition.run_competition = Mock(return_value=competition_result)
    broadcast.assemble = Mock(return_value="record")

    cycle = SelectionBroadcastCycle(
        workspace=workspace,
        competition=competition,
        broadcast=broadcast,
        buffer=buffer,
        store=store,
        vector_index=index,
        goal_manager=goal_manager,
    )

    item = MemoryItem(id="seed", content="fruit fact")
    cycle.enqueue_for_competition(item)
    record = cycle.run_competition_dry(n_slots=1)
    _ = cycle.inspect("stats")

    assert len(cycle.buffer.top(k=1)) == 1
    competition.run_competition.assert_called_once()
    assert record is competition_result
    store.update_state.assert_called_once_with(item.id, ActivationState.PRECONSCIOUS)
    assert cycle.buffer.all_items()[0] is item
    index.query.assert_called_once()
    assert "broadcasts" in _


def test_server_builds_cycle_with_infrastructure_ports(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {}

    def fake_goal_manager(store: object, embedder: object) -> object:
        calls["goal_manager"] = {
            "store": store,
            "embedder": embedder,
        }
        manager = Mock()
        manager.active_goals = []
        calls["goal_manager_instance"] = manager
        return manager

    def fake_ingestion(store: object, vector_index: object, embedder: object) -> object:
        calls["ingestion"] = {
            "store": store,
            "vector_index": vector_index,
            "embedder": embedder,
        }
        return Mock()

    def fake_cycle(
        workspace: object,
        competition: object,
        broadcast: object,
        buffer: object,
        store: object,
        vector_index: object,
        goal_manager: object,
    ) -> object:
        calls["cycle"] = {
            "store": store,
            "vector_index": vector_index,
            "goal_manager": goal_manager,
            "workspace": workspace,
            "buffer": buffer,
            "broadcast": broadcast,
            "competition": competition,
        }
        cycle = Mock()
        cycle.workspace = workspace
        cycle.buffer = buffer
        cycle.goal_manager = goal_manager
        return cycle

    config = GWTConfig(data_dir=tmp_path / "wire")
    config.ensure_data_dir()
    config.embedding_dim = 4

    monkeypatch.setattr("gwt_context.server.GoalManager", fake_goal_manager)
    monkeypatch.setattr("gwt_context.server.IngestionPipeline", fake_ingestion)
    monkeypatch.setattr("gwt_context.server.SelectionBroadcastCycle", fake_cycle)
    monkeypatch.setattr("gwt_context.server.register_tools", lambda *args, **kwargs: None)
    monkeypatch.setattr("gwt_context.server.register_resources", lambda *args, **kwargs: None)
    def fake_embedder(*_args: object, **_kwargs: object) -> object:
        return Mock()

    monkeypatch.setattr(
        "gwt_context.server.SentenceTransformerEmbedder", fake_embedder
    )

    create_server(config)

    goal = calls["goal_manager"]
    ingestion = calls["ingestion"]
    cycle = calls["cycle"]

    assert goal["store"] is ingestion["store"]
    assert goal["embedder"] is ingestion["embedder"]
    assert cycle["store"] is goal["store"]
    assert cycle["vector_index"] is ingestion["vector_index"]
    assert cycle["goal_manager"] is calls["goal_manager_instance"]

    assert isinstance(cycle["store"], SQLiteMemoryStore)
    assert isinstance(cycle["vector_index"], VectorIndex)
