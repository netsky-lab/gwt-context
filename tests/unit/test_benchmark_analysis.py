"""Tests for benchmark result analysis helpers."""

from tests.benchmarks.analyze_results import format_markdown, summarize_report


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
    assert summary["buckets"]["gwt_only_correct"] == 1
    assert "demo - model-x" in format_markdown([summary])
