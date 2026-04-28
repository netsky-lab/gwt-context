"""Snapshot-style checks for public MCP tool contracts."""

from gwt_context.infrastructure.config import GWTConfig
from gwt_context.server import create_server

EXPECTED_TOOLS = {
    "gwt_attend",
    "gwt_broadcast",
    "gwt_bus_inspect",
    "gwt_collection_query",
    "gwt_compete",
    "gwt_evict",
    "gwt_inspect",
    "gwt_link",
    "gwt_query",
    "gwt_resolve",
    "gwt_set_goal",
    "gwt_store",
    "gwt_trace_explain",
}


def _build_ready_mcp(tmp_path):  # type: ignore[no-untyped-def]
    return create_server(
        GWTConfig(
            data_dir=str(tmp_path),
            embedding_provider="hash",
            embedding_model="hash",
            embedding_dim=16,
            workspace_capacity=3,
        )
    )


def _tool_call(mcp, name):  # type: ignore[no-untyped-def]
    return mcp._tool_manager.get_tool(name).fn


def test_registered_tool_names_are_stable(tmp_path) -> None:
    mcp = _build_ready_mcp(tmp_path)

    for tool_name in EXPECTED_TOOLS:
        assert mcp._tool_manager.get_tool(tool_name) is not None


def test_core_tool_response_key_contracts_are_stable(tmp_path) -> None:
    mcp = _build_ready_mcp(tmp_path)
    gwt_store = _tool_call(mcp, "gwt_store")
    gwt_query = _tool_call(mcp, "gwt_query")
    gwt_resolve = _tool_call(mcp, "gwt_resolve")
    gwt_collection_query = _tool_call(mcp, "gwt_collection_query")
    gwt_attend = _tool_call(mcp, "gwt_attend")
    gwt_trace_explain = _tool_call(mcp, "gwt_trace_explain")
    gwt_bus_inspect = _tool_call(mcp, "gwt_bus_inspect")

    store = gwt_store("Idea-001 | type=twitter | topic=GWT | score=9 | status=ready")
    query = gwt_query("GWT", k=1)
    resolve = gwt_resolve("How many ideas have status = 'ready'?", planner="structured")
    collection = gwt_collection_query("top_k", metric="score", k=1)
    attend = gwt_attend("How many ideas have status = 'ready'?", planner="structured")
    trace = gwt_trace_explain()
    bus = gwt_bus_inspect()

    assert set(store) == {"id", "memory_type", "activation_state", "linked_to", "status"}
    assert set(query[0]) == {
        "id",
        "content",
        "memory_type",
        "activation_state",
        "activation_level",
        "linked_ids",
        "tags",
        "admitted",
    }
    assert {"question", "planner", "context_count", "evidence_plan"} <= set(resolve)
    assert {
        "operation",
        "answer",
        "matched_count",
        "matched_records",
        "supporting_evidence",
        "metadata",
    } <= set(collection)
    assert {
        "question",
        "planner",
        "supported_planners",
        "context_count",
        "passes_requested",
        "passes_completed",
        "admit",
        "evidence_plan",
        "tool_call_count",
        "admitted_ids",
        "broadcast",
        "workspace",
        "trace",
    } <= set(attend)
    assert {
        "status",
        "question",
        "planner",
        "strategy",
        "answer",
        "pass_count",
        "tool_call_count",
        "phases",
        "explanation",
        "trace",
    } <= set(trace)
    assert {"status", "broadcast_bus", "summary"} <= set(bus)
