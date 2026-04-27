"""Tests for benchmark result analysis helpers."""

from tests.benchmarks.analyze_results import (
    classify_gwt_failure,
    format_markdown,
    summarize_report,
)


def test_summarize_report_compares_gwt_and_baseline() -> None:
    report = {
        "_path": "result.json",
        "benchmark_name": "demo",
        "model": "model-x",
        "results": [
            {
                "task_id": "t1",
                "mode": "gwt",
                "correct": True,
                "latency_seconds": 2.0,
                "tool_calls": 3,
                "total_tokens": 10,
                "workspace_snapshot": {
                    "workspace": {
                        "occupied_count": 2,
                        "items": [
                            {"content": "Ada's advisor was Grace", "empty": False},
                            {"content": "distractor", "empty": False},
                        ],
                    }
                },
                "expected_evidence": ["Ada's advisor was Grace"],
            },
            {
                "task_id": "t1",
                "mode": "baseline",
                "correct": False,
                "latency_seconds": 1.0,
                "tool_calls": 0,
                "total_tokens": 5,
            },
        ],
    }

    summary = summarize_report(report)

    assert summary["gwt_accuracy"] == 1.0
    assert summary["baseline_accuracy"] == 0.0
    assert summary["avg_gwt_tool_calls"] == 3.0
    assert summary["gwt_token_reduction_pct"] == -100.0
    assert summary["gwt_latency_ratio"] == 2.0
    assert summary["avg_workspace_occupied"] == 2.0
    assert summary["avg_evidence_precision"] == 0.5
    assert summary["avg_evidence_recall"] == 1.0
    assert summary["buckets"]["gwt_only_correct"] == 1
    rendered = format_markdown([summary])
    assert "## Comparison Table" in rendered
    assert "| Benchmark | Mode | Tasks | GWT acc | Baseline acc |" in rendered
    assert "demo - model-x" in rendered


def test_classify_gwt_failure_detects_tool_loop_pathologies() -> None:
    assert classify_gwt_failure({"correct": True}) == "correct"
    assert classify_gwt_failure({"correct": False, "error": "max_tool_rounds"}) == (
        "max_tool_rounds"
    )
    assert classify_gwt_failure(
        {
            "correct": False,
            "predicted": "<channel|><|tool_call>call:gwt_broadcast{}<tool_call|>",
            "tool_calls": 2,
        }
    ) == "tool_markup_as_answer"
    assert classify_gwt_failure(
        {
            "correct": False,
            "predicted": "wrong",
            "tool_calls": 3,
            "trace": [{"phase": "model", "finish_reason": "tool_calls"}],
        }
    ) == "wrong_after_tool_loop"
