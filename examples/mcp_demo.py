"""Minimal MCP-facing GWT demo with deterministic local embeddings."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

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


class DemoEmbedder:
    """Tiny deterministic embedder so the demo runs without model downloads."""

    @property
    def dim(self) -> int:
        return 4

    def embed(self, text: str) -> list[float]:
        value = sum(ord(char) for char in text)
        return [
            (value % 13) / 13.0,
            ((value // 13) % 13) / 13.0,
            ((value // 169) % 13) / 13.0,
            ((value // 2197) % 13) / 13.0,
        ]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


def build_demo_mcp(data_dir: Path) -> FastMCP:
    """Build a local MCP server object wired to real application services."""
    store = SQLiteMemoryStore(db_path=data_dir / "demo.db")
    vector_index = VectorIndex(dim=4, path=data_dir / "vectors.bin")
    embedder = DemoEmbedder()
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
    mcp = FastMCP("gwt-context-demo")
    attention_trace = AttentionTraceStore()
    register_tools(mcp, cycle, ingestion, attention_trace)
    register_resources(mcp, cycle, store, attention_trace)
    return mcp


def run_demo() -> dict[str, Any]:
    """Run a deterministic MCP tool/resource scenario and return key outputs."""
    with tempfile.TemporaryDirectory() as tmp:
        mcp = build_demo_mcp(Path(tmp))
        gwt_store = _tool_call(mcp, "gwt_store")
        gwt_set_goal = _tool_call(mcp, "gwt_set_goal")
        gwt_query = _tool_call(mcp, "gwt_query")
        gwt_attend = _tool_call(mcp, "gwt_attend")
        gwt_broadcast = _tool_call(mcp, "gwt_broadcast")
        gwt_inspect = _tool_call(mcp, "gwt_inspect")

        stored = [
            gwt_store("Ada Lovelace's doctoral advisor was Grace Hopper at MIT"),
            gwt_store("Grace Hopper's doctoral advisor was Alan Turing at Cambridge"),
            gwt_store("The cafeteria menu changed on Tuesday"),
        ]
        goal = gwt_set_goal(
            "Find the doctoral advisor chain for Ada Lovelace",
            keywords=["Ada", "doctoral", "advisor"],
        )
        query = gwt_query("Ada Lovelace doctoral advisor", k=2)
        attend = gwt_attend(
            question="Find the doctoral advisor chain for Ada Lovelace",
            keywords=["Ada", "doctoral", "advisor"],
            k=2,
            passes=2,
        )
        broadcast = gwt_broadcast()
        stats = gwt_inspect("stats")
        workspace = _call_resource(mcp, "gwt://workspace")
        last_attention = _call_resource(mcp, "gwt://attention/last")
        return {
            "stored_ids": [item["id"] for item in stored],
            "goal": goal,
            "query_count": len(query),
            "attend": attend,
            "broadcast": broadcast,
            "stats": stats,
            "workspace": workspace,
            "last_attention": last_attention,
        }


def _tool_call(mcp: FastMCP, name: str):
    return mcp._tool_manager.get_tool(name).fn


def _call_resource(mcp: FastMCP, uri: str) -> str:
    async def runner() -> str:
        resource = await mcp._resource_manager.get_resource(uri)
        return resource.fn()  # type: ignore[attr-defined]

    return asyncio.run(runner())


def main() -> None:
    """Print the demo broadcast and compact stats."""
    result = run_demo()
    print(result["broadcast"])
    print()
    print(f"Stored: {len(result['stored_ids'])}")
    print(f"Query matches: {result['query_count']}")
    print(f"Attend strategy: {result['attend']['evidence_plan']['strategy']}")
    print(f"Stats: {result['stats']}")


if __name__ == "__main__":
    main()
