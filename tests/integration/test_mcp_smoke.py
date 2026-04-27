"""MCP smoke test over public tool/resource registrations."""

import asyncio
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from gwt_context.application.attention import AttentionTraceStore
from gwt_context.application.cycle import PreconsciousBuffer, SelectionBroadcastCycle
from gwt_context.application.goal_manager import GoalManager
from gwt_context.application.ingestion import IngestionPipeline
from gwt_context.domain.broadcast import BroadcastAssembler
from gwt_context.domain.competition import CompetitionEngine
from gwt_context.domain.specialists import create_default_specialists
from gwt_context.domain.workspace import GlobalWorkspace
from gwt_context.infrastructure.storage import SQLiteMemoryStore
from gwt_context.infrastructure.vector_index import VectorIndex
from gwt_context.mcp.resources import register_resources
from gwt_context.mcp.tools import register_tools


class FakeEmbedder:
    """Small deterministic embedder for MCP smoke coverage."""

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


def _build_mcp(tmp_path: Path) -> FastMCP:
    store = SQLiteMemoryStore(db_path=tmp_path / "mcp-smoke.db")
    vector_index = VectorIndex(dim=4, path=tmp_path / "vectors.bin")
    embedder = FakeEmbedder()
    workspace = GlobalWorkspace(capacity=3)
    cycle = SelectionBroadcastCycle(
        workspace=workspace,
        competition=CompetitionEngine(specialists=create_default_specialists()),
        broadcast=BroadcastAssembler(),
        buffer=PreconsciousBuffer(max_size=20),
        store=store,
        vector_index=vector_index,
        goal_manager=GoalManager(store=store, embedder=embedder),
    )
    ingestion = IngestionPipeline(
        store=store,
        vector_index=vector_index,
        embedder=embedder,
    )
    mcp = FastMCP("gwt-context-smoke")
    attention_trace = AttentionTraceStore()
    register_tools(mcp, cycle, ingestion, attention_trace)
    register_resources(mcp, cycle, store, attention_trace)
    return mcp


def _tool_call(mcp: FastMCP, name: str):
    return mcp._tool_manager.get_tool(name).fn


def _call_resource(mcp: FastMCP, uri: str) -> str:
    async def runner() -> str:
        resource = await mcp._resource_manager.get_resource(uri)
        return resource.fn()  # type: ignore[attr-defined]

    return asyncio.run(runner())


def test_mcp_tool_and_resource_smoke(tmp_path: Path) -> None:
    mcp = _build_mcp(tmp_path)

    stored = _tool_call(mcp, "gwt_store")(
        content="Ada Lovelace's doctoral advisor was Grace Hopper at MIT",
        tags=["smoke"],
    )
    goal = _tool_call(mcp, "gwt_set_goal")(
        description="Find Ada Lovelace's doctoral advisor",
        keywords=["Ada", "advisor"],
    )
    query_results = _tool_call(mcp, "gwt_query")(query="Ada doctoral advisor", k=1)
    admitted_query_results = _tool_call(mcp, "gwt_query")(
        query="Ada doctoral advisor",
        k=1,
        admit=True,
    )
    attend = _tool_call(mcp, "gwt_attend")(
        question="Find Ada Lovelace's doctoral advisor",
        keywords=["Ada", "advisor"],
        k=1,
        passes=2,
    )
    broadcast = _tool_call(mcp, "gwt_broadcast")()
    stats = _tool_call(mcp, "gwt_inspect")(target="stats")
    workspace_resource = _call_resource(mcp, "gwt://workspace")
    slots_resource = _call_resource(mcp, "gwt://workspace/slots")
    last_attention_resource = _call_resource(mcp, "gwt://attention/last")

    assert stored["status"] == "stored and ready for competition"
    assert goal["status"].startswith("goal set")
    assert query_results[0]["id"] == stored["id"]
    assert admitted_query_results[0]["admitted"] is True
    assert attend["evidence_plan"]["strategy"] == "generic_semantic_query_planner"
    assert attend["passes_completed"] == 2
    assert "Ada Lovelace" in attend["broadcast"]
    assert "Find Ada Lovelace" in last_attention_resource
    assert "Ada Lovelace" in broadcast
    assert stats["total_items"] == 1
    assert "Ada Lovelace" in workspace_resource
    assert "Slot 0:" in slots_resource
