"""Summarize benchmark JSON artifacts."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_reports(paths: list[Path]) -> list[dict[str, Any]]:
    """Load benchmark report JSON files."""
    reports = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            report = json.load(f)
        report["_path"] = str(path)
        reports.append(report)
    return reports


def summarize_report(report: dict[str, Any]) -> dict[str, Any]:
    """Build a compact report summary with GWT/baseline deltas."""
    pairs: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for result in report.get("results", []):
        pairs[result["task_id"]][result["mode"]] = result

    buckets = {
        "both_correct": 0,
        "gwt_only_correct": 0,
        "baseline_only_correct": 0,
        "both_wrong": 0,
    }
    gwt_results = []
    baseline_results = []
    examples = []
    failure_buckets: dict[str, int] = defaultdict(int)

    for task_id, pair in pairs.items():
        gwt = pair.get("gwt")
        baseline = pair.get("baseline")
        if gwt is None or baseline is None:
            continue

        gwt_results.append(gwt)
        baseline_results.append(baseline)
        if gwt["correct"] and baseline["correct"]:
            buckets["both_correct"] += 1
        elif gwt["correct"]:
            buckets["gwt_only_correct"] += 1
        elif baseline["correct"]:
            buckets["baseline_only_correct"] += 1
        else:
            buckets["both_wrong"] += 1

        failure_kind = classify_gwt_failure(gwt)
        if failure_kind != "correct":
            failure_buckets[failure_kind] += 1

        if len(examples) < 5 and (not gwt["correct"] or not baseline["correct"]):
            examples.append(
                {
                    "task_id": task_id,
                    "expected": gwt.get("expected", baseline.get("expected", "")),
                    "gwt_predicted": gwt.get("predicted", ""),
                    "baseline_predicted": baseline.get("predicted", ""),
                    "gwt_tool_calls": gwt.get("tool_calls", 0),
                    "gwt_error": gwt.get("error", ""),
                    "baseline_error": baseline.get("error", ""),
                }
            )

    avg_gwt_tokens = _average([r.get("total_tokens", 0) for r in gwt_results])
    avg_baseline_tokens = _average([r.get("total_tokens", 0) for r in baseline_results])
    avg_gwt_latency = _average([r.get("latency_seconds", 0.0) for r in gwt_results])
    avg_baseline_latency = _average(
        [r.get("latency_seconds", 0.0) for r in baseline_results]
    )
    evidence_precision, evidence_recall = _evidence_summary(gwt_results)
    return {
        "path": report.get("_path", ""),
        "benchmark_name": report.get("benchmark_name", ""),
        "model": report.get("model", ""),
        "gwt_mode": report.get("gwt_mode", "tools"),
        "task_count": len(gwt_results),
        "gwt_accuracy": _accuracy(gwt_results),
        "baseline_accuracy": _accuracy(baseline_results),
        "avg_gwt_latency": avg_gwt_latency,
        "avg_baseline_latency": avg_baseline_latency,
        "avg_gwt_tool_calls": _average([r.get("tool_calls", 0) for r in gwt_results]),
        "avg_gwt_tokens": avg_gwt_tokens,
        "avg_baseline_tokens": avg_baseline_tokens,
        "gwt_token_reduction_pct": _reduction_pct(avg_baseline_tokens, avg_gwt_tokens),
        "gwt_latency_ratio": _ratio(avg_gwt_latency, avg_baseline_latency),
        "avg_workspace_occupied": _average_workspace_occupied(gwt_results),
        "avg_evidence_precision": evidence_precision,
        "avg_evidence_recall": evidence_recall,
        "buckets": buckets,
        "failure_buckets": dict(sorted(failure_buckets.items())),
        "examples": examples,
    }


def classify_gwt_failure(result: dict[str, Any]) -> str:
    """Classify why a GWT result failed, using trace and answer fields."""
    if result.get("correct"):
        return "correct"
    if result.get("error") == "max_tool_rounds":
        return "max_tool_rounds"
    if result.get("error"):
        return "runtime_error"

    predicted = str(result.get("predicted", ""))
    raw_answer = str(result.get("raw_answer", ""))
    combined = f"{predicted}\n{raw_answer}"
    if "<tool_call" in combined or "<channel|>" in combined:
        return "tool_markup_as_answer"
    if not predicted.strip():
        return "empty_answer"
    if int(result.get("tool_calls", 0)) == 0:
        return "premature_no_tool_answer"

    trace = result.get("trace", [])
    if any(entry.get("error") for entry in trace if isinstance(entry, dict)):
        return "tool_error"
    if any(
        entry.get("phase") == "model" and entry.get("finish_reason") == "tool_calls"
        for entry in trace
        if isinstance(entry, dict)
    ):
        return "wrong_after_tool_loop"
    return "wrong_answer"


def format_markdown(summaries: list[dict[str, Any]]) -> str:
    """Render summaries as Markdown."""
    lines = ["# Benchmark Result Summary", ""]
    if summaries:
        lines.extend(
            [
                "## Comparison Table",
                "",
                "| Benchmark | Mode | Tasks | GWT acc | Baseline acc | "
                "Evidence recall | Evidence precision | Token delta |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for summary in summaries:
            lines.append(
                "| "
                f"{summary['benchmark_name']} | "
                f"{summary['gwt_mode']} | "
                f"{summary['task_count']} | "
                f"{summary['gwt_accuracy']:.1%} | "
                f"{summary['baseline_accuracy']:.1%} | "
                f"{summary['avg_evidence_recall']:.1%} | "
                f"{summary['avg_evidence_precision']:.1%} | "
                f"{summary['gwt_token_reduction_pct']:+.1f}% |"
            )
        lines.append("")

    for summary in summaries:
        lines.extend(
            [
                f"## {summary['benchmark_name']} - {summary['model']} ({summary['gwt_mode']})",
                "",
                f"- Source: `{summary['path']}`",
                f"- Tasks: {summary['task_count']}",
                f"- GWT accuracy: {summary['gwt_accuracy']:.1%}",
                f"- Baseline accuracy: {summary['baseline_accuracy']:.1%}",
                f"- Avg GWT latency: {summary['avg_gwt_latency']:.2f}s",
                f"- Avg baseline latency: {summary['avg_baseline_latency']:.2f}s",
                f"- Avg GWT tool calls: {summary['avg_gwt_tool_calls']:.2f}",
                f"- Avg GWT tokens: {summary['avg_gwt_tokens']:.1f}",
                f"- Avg baseline tokens: {summary['avg_baseline_tokens']:.1f}",
                f"- GWT token reduction vs baseline: {summary['gwt_token_reduction_pct']:+.1f}%",
                f"- GWT/baseline latency ratio: {summary['gwt_latency_ratio']:.2f}x",
                f"- Avg workspace occupied: {summary['avg_workspace_occupied']:.2f}",
                f"- Avg evidence precision: {summary['avg_evidence_precision']:.1%}",
                f"- Avg evidence recall: {summary['avg_evidence_recall']:.1%}",
                "",
                "Outcome buckets:",
            ]
        )
        for name, count in summary["buckets"].items():
            lines.append(f"- {name}: {count}")

        if summary["failure_buckets"]:
            lines.extend(["", "GWT failure buckets:"])
            for name, count in summary["failure_buckets"].items():
                lines.append(f"- {name}: {count}")

        if summary["examples"]:
            lines.extend(["", "Delta examples:"])
            for example in summary["examples"]:
                lines.append(
                    "- "
                    f"{example['task_id']}: expected={example['expected']!r}, "
                    f"gwt={example['gwt_predicted']!r}, "
                    f"baseline={example['baseline_predicted']!r}, "
                    f"tool_calls={example['gwt_tool_calls']}"
                )
        lines.append("")
    return "\n".join(lines)


def _accuracy(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    return sum(1 for result in results if result.get("correct")) / len(results)


def _average(values: list[float | int]) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / len(values)


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _reduction_pct(baseline: float, measured: float) -> float:
    if baseline == 0:
        return 0.0
    return (baseline - measured) / baseline * 100


def _average_workspace_occupied(results: list[dict[str, Any]]) -> float:
    counts = []
    for result in results:
        workspace = result.get("workspace_snapshot", {}).get("workspace", {})
        counts.append(workspace.get("occupied_count", 0))
    return _average(counts)


def _evidence_summary(results: list[dict[str, Any]]) -> tuple[float, float]:
    precisions = []
    recalls = []
    for result in results:
        if "evidence_precision" in result and "evidence_recall" in result:
            precisions.append(float(result.get("evidence_precision", 0.0)))
            recalls.append(float(result.get("evidence_recall", 0.0)))
            continue
        expected = [str(item) for item in result.get("expected_evidence", []) if item]
        workspace_items = result.get("workspace_snapshot", {}).get("workspace", {}).get("items", [])
        contents = [
            str(item.get("content", ""))
            for item in workspace_items
            if isinstance(item, dict) and not item.get("empty") and item.get("content")
        ]
        if not expected or not contents:
            continue
        matched_expected = [
            evidence
            for evidence in expected
            if any(_evidence_matches(evidence, content) for content in contents)
        ]
        relevant_contents = [
            content
            for content in contents
            if any(_evidence_matches(evidence, content) for evidence in expected)
        ]
        precisions.append(len(relevant_contents) / len(contents))
        recalls.append(len(matched_expected) / len(expected))
    return _average(precisions), _average(recalls)


def _evidence_matches(expected: str, content: str) -> bool:
    expected_norm = " ".join(expected.lower().split())
    content_norm = " ".join(content.lower().split())
    return expected_norm in content_norm or content_norm in expected_norm


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize benchmark result JSON files")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    paths: list[Path] = []
    for entry in args.paths:
        if entry.is_dir():
            paths.extend(sorted(entry.glob("*.json")))
        else:
            paths.append(entry)

    reports = load_reports(paths)
    summaries = [summarize_report(report) for report in reports]
    print(format_markdown(summaries))


if __name__ == "__main__":
    main()
