"""GWT-Context MCP server — wiring and entry point.

Assembles all components (DI container style) and starts the MCP server.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from gwt_context.application.attention import AttentionTraceStore
from gwt_context.application.cycle import PreconsciousBuffer, SelectionBroadcastCycle
from gwt_context.application.goal_manager import GoalManager
from gwt_context.application.ingestion import IngestionPipeline
from gwt_context.domain.broadcast import BroadcastAssembler
from gwt_context.domain.competition import CompetitionEngine
from gwt_context.domain.specialists import create_default_specialists
from gwt_context.domain.workspace import GlobalWorkspace
from gwt_context.infrastructure.config import GWTConfig
from gwt_context.infrastructure.embeddings import HashEmbeddingEmbedder, SentenceTransformerEmbedder
from gwt_context.infrastructure.storage import SQLiteMemoryStore
from gwt_context.infrastructure.vector_index import VectorIndex
from gwt_context.interfaces.ports import EmbeddingPort
from gwt_context.mcp.resources import register_resources
from gwt_context.mcp.tools import register_tools


def create_server(config: GWTConfig | None = None) -> FastMCP:
    """Assemble all components and create the MCP server.

    This is the composition root — all dependencies are wired here.
    """
    if config is None:
        config = GWTConfig.from_env()

    config.ensure_data_dir()

    # --- Infrastructure ---
    embedder = _build_embedder(config)
    store = SQLiteMemoryStore(db_path=config.db_path)
    vector_index = VectorIndex(
        dim=config.embedding_dim,
        max_elements=config.max_vector_elements,
        path=config.vector_index_path,
    )

    # --- Domain ---
    workspace = GlobalWorkspace(capacity=config.workspace_capacity)
    specialists = create_default_specialists()
    competition = CompetitionEngine(
        specialists=specialists,
        goal_modulation_strength=config.goal_modulation_strength,
    )
    broadcast = BroadcastAssembler(max_tokens=config.max_broadcast_tokens)

    # --- Application ---
    buffer = PreconsciousBuffer(max_size=config.buffer_size)
    goal_manager = GoalManager(store=store, embedder=embedder)
    ingestion = IngestionPipeline(
        store=store,
        vector_index=vector_index,
        embedder=embedder,
    )
    cycle = SelectionBroadcastCycle(
        workspace=workspace,
        competition=competition,
        broadcast=broadcast,
        buffer=buffer,
        store=store,
        vector_index=vector_index,
        goal_manager=goal_manager,
    )
    attention_trace = AttentionTraceStore()

    # Restore workspace state from DB on startup
    _restore_state(store, workspace, buffer, vector_index)

    # --- MCP Server ---
    mcp = FastMCP(
        name="gwt-context",
    )

    register_tools(mcp, cycle, ingestion, attention_trace)
    register_resources(mcp, cycle, store, attention_trace)

    return mcp


def _build_embedder(config: GWTConfig) -> EmbeddingPort:
    provider = config.embedding_provider.lower().strip()
    model_name = config.embedding_model.lower().strip()
    if provider in {"hash", "deterministic", "local-hash"} or model_name in {
        "hash",
        "deterministic",
        "local-hash",
    }:
        return HashEmbeddingEmbedder(dim=config.embedding_dim)
    return SentenceTransformerEmbedder(model_name=config.embedding_model)


def _restore_state(
    store: SQLiteMemoryStore,
    workspace: GlobalWorkspace,
    buffer: PreconsciousBuffer,
    vector_index: VectorIndex,
) -> None:
    """Restore workspace, buffer, and vector index from persistent storage."""
    from gwt_context.domain.models import ActivationState

    # Restore conscious items to workspace
    conscious_items = store.get_items_by_state(ActivationState.CONSCIOUS)
    for item in conscious_items[:workspace.capacity]:
        workspace.admit(item)

    # Restore preconscious items to buffer
    preconscious_items = store.get_items_by_state(ActivationState.PRECONSCIOUS)
    buffer.push_many(preconscious_items)

    # Rebuild vector index if empty but DB has items with embeddings
    if vector_index.count == 0:
        all_items = store.get_all_items()
        for item in all_items:
            if item.embedding is not None:
                vector_index.add(item.id, item.embedding)
        if vector_index.count > 0:
            vector_index.save()


def main() -> None:
    """Entry point for `gwt-context` command."""
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
