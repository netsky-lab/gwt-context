"""Tests for benchmark trace HTML rendering."""

from tests.benchmarks.render_trace import render_report


def test_render_report_includes_task_trace_and_workspace() -> None:
    html = render_report(
        {
            "benchmark_name": "demo",
            "model": "m",
            "gwt_mode": "hybrid",
            "run_id": "run",
            "task_count": 1,
            "gwt_accuracy": 1.0,
            "baseline_accuracy": 0.0,
            "results": [
                {
                    "mode": "gwt",
                    "task_id": "t1",
                    "correct": True,
                    "expected": "A",
                    "predicted": "A",
                    "raw_answer": "ANSWER: A",
                    "trace": [
                        {"phase": "controller", "evidence": {"answer": "A"}},
                        {
                            "phase": "broadcast_bus",
                            "result": {
                                "proposals": [
                                    {
                                        "subscriber": "structured_resolver",
                                        "kind": "resolve_answer",
                                    },
                                    {
                                        "subscriber": "semantic_recall",
                                        "kind": "query_memory",
                                        "payload": {"query": "Ada advisor"},
                                        "rationale": "duplicate recall",
                                    },
                                ],
                                "accepted": [
                                    {
                                        "subscriber": "structured_resolver",
                                        "kind": "resolve_answer",
                                    }
                                ],
                                "inhibited": [
                                    {
                                        "subscriber": "semantic_recall",
                                        "kind": "query_memory",
                                        "payload": {"query": "Ada advisor"},
                                        "rationale": "duplicate recall",
                                    }
                                ],
                                "subscriber_reports": [
                                    {
                                        "subscriber": "structured_resolver",
                                        "status": "ok",
                                        "proposal_count": 1,
                                        "elapsed_ms": 0.1,
                                    }
                                ],
                            },
                        },
                        {"phase": "broadcast_bus_tool", "kind": "resolve_answer"},
                        {
                            "phase": "subscriber_policy_skip",
                            "kind": "query_memory",
                            "workspace_after": {
                                "occupied_count": 1,
                                "items": [{"content": "resolved answer", "empty": False}],
                            },
                        },
                    ],
                    "workspace_snapshot": {"workspace": {"items": []}},
                }
            ],
        }
    )

    assert "demo | m | hybrid" in html
    assert "ANSWER: A" in html
    assert "controller" in html
    assert "Broadcast Bus" in html
    assert "structured_resolver" in html
    assert "Trace phases:" in html
    assert "controller x1" in html
    assert "actions=1" in html
    assert "policy_skips=1" in html
    assert "Proposal Groups" in html
    assert "semantic_recall / query_memory" in html
    assert "Inhibited Proposals" in html
    assert "Ada advisor" in html
    assert "Workspace Changes" in html
