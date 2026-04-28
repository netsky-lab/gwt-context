"""Tests for benchmark result analysis helpers."""

from tests.benchmarks.analyze_results import (
    classify_gwt_failure,
    format_markdown,
    summarize_bus_pairs,
    summarize_report,
)
from tests.benchmarks.bus_matrix import build_bus_matrix_commands, summarize_bus_matrix


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
    assert summary["family_metrics"]["unknown"]["accuracy"] == 1.0
    assert summary["buckets"]["gwt_only_correct"] == 1
    rendered = format_markdown([summary])
    assert "## Comparison Table" in rendered
    assert "| Benchmark | Mode | Tasks | GWT acc | Baseline acc |" in rendered
    assert "## Release Gates" not in rendered
    assert "demo - model-x" in rendered


def test_format_markdown_renders_release_gates_for_known_task_families() -> None:
    summary = summarize_report(
        {
            "_path": "result.json",
            "benchmark_name": "longbench_pro",
            "model": "model-x",
            "results": [
                {
                    "task_id": "lbp_topk_30rec_0",
                    "mode": "gwt",
                    "correct": True,
                    "latency_seconds": 1.0,
                    "tool_calls": 2,
                    "total_tokens": 0,
                    "workspace_snapshot": {"workspace": {"occupied_count": 1, "items": []}},
                },
                {
                    "task_id": "lbp_topk_30rec_0",
                    "mode": "baseline",
                    "correct": False,
                    "latency_seconds": 1.0,
                    "tool_calls": 0,
                    "total_tokens": 10,
                },
            ],
        }
    )

    rendered = format_markdown([summary])

    assert "## Release Gates" in rendered
    assert "| top_k | pass | 100.0% | 80.0% |" in rendered


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


def test_summarize_report_counts_broadcast_bus_metrics() -> None:
    summary = summarize_report(
        {
            "_path": "bus-on.json",
            "benchmark_name": "ruler_multi_hop",
            "model": "model-x",
            "gwt_mode": "attend",
            "attend_broadcast_bus": True,
            "results": [
                {
                    "task_id": "ruler_advisor_2hop_0",
                    "mode": "gwt",
                    "correct": True,
                    "latency_seconds": 1.0,
                    "tool_calls": 3,
                    "total_tokens": 0,
                    "trace": [
                        {
                            "phase": "broadcast_bus",
                            "result": {
                                "proposals": [{}, {}],
                                "accepted": [{}],
                                "inhibited": [{}],
                                "subscriber_reports": [
                                    {"subscriber": "s", "status": "ok"},
                                    {"subscriber": "t", "status": "timeout"},
                                ],
                            },
                        },
                        {"phase": "broadcast_bus_tool"},
                    ],
                },
                {
                    "task_id": "ruler_advisor_2hop_0",
                    "mode": "baseline",
                    "correct": True,
                    "latency_seconds": 1.0,
                    "tool_calls": 0,
                    "total_tokens": 0,
                },
            ],
        }
    )

    assert summary["bus_proposals"] == 2
    assert summary["bus_accepted"] == 1
    assert summary["bus_inhibited"] == 1
    assert summary["bus_timeouts"] == 1
    assert summary["bus_tool_actions"] == 1


def test_summarize_bus_pairs_compares_attend_on_off() -> None:
    on = {
        "benchmark_name": "demo",
        "model": "m",
        "gwt_mode": "attend",
        "attend_broadcast_bus": True,
        "task_count": 1,
        "gwt_accuracy": 1.0,
        "avg_gwt_tool_calls": 3.0,
        "bus_accepted": 2,
    }
    off = {
        **on,
        "attend_broadcast_bus": False,
        "gwt_accuracy": 0.0,
        "avg_gwt_tool_calls": 2.0,
        "bus_accepted": 0,
    }

    rows = summarize_bus_pairs([on, off])

    assert rows == [
        {
            "benchmark_name": "demo",
            "model": "m",
            "task_count": 1,
            "accuracy_delta": 1.0,
            "tool_call_delta": 1.0,
            "accepted_delta": 2,
        }
    ]


def test_bus_matrix_builds_on_off_commands(tmp_path) -> None:
    commands = build_bus_matrix_commands(max_tasks=2)

    assert {command.bus_enabled for command in commands} == {True, False}
    assert all("--gwt-mode" in command.command for command in commands)

    report_path = tmp_path / "report.json"
    report_path.write_text(
        """
        {
          "benchmark_name": "demo",
          "model": "m",
          "gwt_mode": "attend",
          "attend_broadcast_bus": true,
          "results": []
        }
        """,
        encoding="utf-8",
    )
    summary = summarize_bus_matrix([report_path])

    assert "markdown" in summary
