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

    return {
        "path": report.get("_path", ""),
        "benchmark_name": report.get("benchmark_name", ""),
        "model": report.get("model", ""),
        "gwt_mode": report.get("gwt_mode", "tools"),
        "task_count": len(gwt_results),
        "gwt_accuracy": _accuracy(gwt_results),
        "baseline_accuracy": _accuracy(baseline_results),
        "avg_gwt_latency": _average([r.get("latency_seconds", 0.0) for r in gwt_results]),
        "avg_baseline_latency": _average(
            [r.get("latency_seconds", 0.0) for r in baseline_results]
        ),
        "avg_gwt_tool_calls": _average([r.get("tool_calls", 0) for r in gwt_results]),
        "avg_gwt_tokens": _average([r.get("total_tokens", 0) for r in gwt_results]),
        "avg_baseline_tokens": _average([r.get("total_tokens", 0) for r in baseline_results]),
        "buckets": buckets,
        "examples": examples,
    }


def format_markdown(summaries: list[dict[str, Any]]) -> str:
    """Render summaries as Markdown."""
    lines = ["# Benchmark Result Summary", ""]
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
                "",
                "Outcome buckets:",
            ]
        )
        for name, count in summary["buckets"].items():
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
