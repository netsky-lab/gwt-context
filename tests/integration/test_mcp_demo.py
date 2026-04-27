"""Regression test for the runnable MCP demo scenario."""

from examples.mcp_demo import run_demo


def test_mcp_demo_runs_end_to_end() -> None:
    result = run_demo()

    assert len(result["stored_ids"]) == 3
    assert result["query_count"] >= 1
    assert result["attend"]["evidence_plan"]["strategy"] == "generic_semantic_query_planner"
    assert "doctoral advisor chain" in result["last_attention"]
    assert result["stats"]["total_items"] == 3
    assert "Ada Lovelace" in result["workspace"]
