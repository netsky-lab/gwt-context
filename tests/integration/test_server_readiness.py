"""Server readiness checks for local/offline startup."""

from gwt_context.infrastructure.config import GWTConfig
from gwt_context.server import create_server
from gwt_context.smoke import run_smoke


def _tool_call(mcp, name):  # type: ignore[no-untyped-def]
    return mcp._tool_manager.get_tool(name).fn


def test_create_server_can_run_tool_workflow_with_hash_embeddings(tmp_path) -> None:
    config = GWTConfig(
        data_dir=str(tmp_path),
        embedding_provider="hash",
        embedding_model="hash",
        embedding_dim=16,
        workspace_capacity=3,
    )
    mcp = create_server(config)

    stored = _tool_call(mcp, "gwt_store")("Paper Alpha -> cites -> Paper Beta")
    resolved = _tool_call(mcp, "gwt_resolve")(
        "What does Paper Alpha cite?",
        planner="graph",
    )

    assert stored["status"] == "stored and ready for competition"
    assert resolved["evidence_plan"]["answer"] == "Paper Beta"


def test_local_smoke_command_reports_successful_runtime_workflow() -> None:
    report = run_smoke()

    assert report["stored_count"] == 3
    assert report["resolve_answer"] == "Paper Gamma"
    assert report["attend_strategy"] == "relation_graph_cites"
    assert report["trace_status"] == "ok"
