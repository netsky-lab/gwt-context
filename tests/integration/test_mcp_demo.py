"""Regression test for the runnable MCP demo scenario."""

from examples.mcp_demo import run_demo


def test_mcp_demo_runs_end_to_end() -> None:
    result = run_demo()

    assert len(result["stored_ids"]) == 3
    assert result["query_count"] >= 1
    assert result["attend"]["evidence_plan"]["strategy"] == "relation_graph_doctoral_advisor"
    assert result["attend"]["evidence_plan"]["answer"] == "Alan Turing"
    assert "doctoral advisor chain" in result["last_attention"]
    assert result["stats"]["total_items"] == 4
    assert "Ada Lovelace" in result["workspace"]
