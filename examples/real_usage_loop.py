"""Run a deterministic in-process MCP usage loop for gwt-context."""

from __future__ import annotations

import json
import tempfile
from typing import Any

from gwt_context.infrastructure.config import GWTConfig
from gwt_context.server import create_server


def run_usage_loop() -> dict[str, Any]:
    """Exercise store, attend, bus inspect, trace explain, and workspace inspect."""
    with tempfile.TemporaryDirectory() as tmp:
        config = GWTConfig(
            data_dir=tmp,
            embedding_provider="hash",
            embedding_model="hash",
            embedding_dim=32,
            workspace_capacity=4,
        )
        mcp = create_server(config)

        gwt_store = _tool_call(mcp, "gwt_store")
        gwt_attend = _tool_call(mcp, "gwt_attend")
        gwt_collection_query = _tool_call(mcp, "gwt_collection_query")
        gwt_bus_inspect = _tool_call(mcp, "gwt_bus_inspect")
        gwt_trace_explain = _tool_call(mcp, "gwt_trace_explain")
        gwt_inspect = _tool_call(mcp, "gwt_inspect")

        graph_items = [
            gwt_store("Paper Alpha -> cites -> Paper Beta", tags=["demo", "graph"]),
            gwt_store("Paper Beta -> cites -> Paper Gamma", tags=["demo", "graph"]),
        ]
        collection_items = [
            gwt_store("emp-001 | name=Ada | team=research | score=9", tags=["demo"]),
            gwt_store("emp-002 | name=Grace | team=platform | score=7", tags=["demo"]),
            gwt_store("emp-003 | name=Alan | team=research | score=6", tags=["demo"]),
        ]

        graph = gwt_attend(
            "What does Paper Alpha cite cite?",
            planner="graph",
            k=3,
            passes=1,
        )
        bus = gwt_bus_inspect().get("broadcast_bus", {}).get("last_result", {})
        collection = gwt_collection_query(operation="top_k", metric="score", k=1)
        trace = gwt_trace_explain()
        workspace = gwt_inspect("workspace")

        return {
            "stored_graph_ids": [item["id"] for item in graph_items],
            "stored_collection_ids": [item["id"] for item in collection_items],
            "graph_answer": graph["evidence_plan"].get("answer", ""),
            "collection_answer": collection.get("answer", ""),
            "bus_accepted": len(bus.get("accepted", [])),
            "bus_inhibited": len(bus.get("inhibited", [])),
            "subscriber_statuses": [
                report.get("status", "") for report in bus.get("subscriber_reports", [])
            ],
            "trace_status": trace.get("status", ""),
            "workspace_size": len(workspace.get("items", [])),
        }


def _tool_call(mcp: Any, name: str) -> Any:
    return mcp._tool_manager.get_tool(name).fn


def main() -> None:
    """Print the deterministic usage loop summary."""
    print(json.dumps(run_usage_loop(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
