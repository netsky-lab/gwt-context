"""Render benchmark trace JSON as a compact HTML report."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def render_report(report: dict[str, Any]) -> str:
    """Render one benchmark report as HTML."""
    title = (
        f"{report.get('benchmark_name', 'benchmark')} | "
        f"{report.get('model', 'model')} | {report.get('gwt_mode', 'tools')}"
    )
    rows = []
    for result in report.get("results", []):
        if result.get("mode") != "gwt":
            continue
        rows.append(_render_result(result))

    return "\n".join(
        [
            "<!doctype html>",
            "<html>",
            "<head>",
            "<meta charset=\"utf-8\">",
            f"<title>{html.escape(title)}</title>",
            "<style>",
            (
                "body{font-family:system-ui,sans-serif;max-width:1100px;"
                "margin:32px auto;line-height:1.45}"
            ),
            "details{border:1px solid #ddd;border-radius:6px;margin:12px 0;padding:10px}",
            "summary{cursor:pointer;font-weight:700}",
            "pre{white-space:pre-wrap;background:#f6f8fa;padding:10px;border-radius:6px}",
            ".ok{color:#177245}.bad{color:#b42318}.meta{color:#555}",
            "</style>",
            "</head>",
            "<body>",
            f"<h1>{html.escape(title)}</h1>",
            _render_summary(report),
            *rows,
            "</body>",
            "</html>",
        ]
    )


def render_to_file(input_path: Path, output_path: Path | None = None) -> Path:
    """Render a JSON report to an HTML file and return the output path."""
    with open(input_path, encoding="utf-8") as f:
        report = json.load(f)
    html_text = render_report(report)
    if output_path is None:
        output_path = input_path.with_suffix(".html")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding="utf-8")
    return output_path


def _render_summary(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "<section>",
            f"<p class=\"meta\">Run: {html.escape(str(report.get('run_id', '')))}</p>",
            "<ul>",
            f"<li>Tasks: {html.escape(str(report.get('task_count', '')))}</li>",
            f"<li>GWT accuracy: {float(report.get('gwt_accuracy', 0.0)):.1%}</li>",
            f"<li>Baseline accuracy: {float(report.get('baseline_accuracy', 0.0)):.1%}</li>",
            "</ul>",
            "</section>",
        ]
    )


def _render_result(result: dict[str, Any]) -> str:
    status_class = "ok" if result.get("correct") else "bad"
    status = "OK" if result.get("correct") else "WRONG"
    trace_html = "\n".join(_render_trace_entry(entry) for entry in result.get("trace", []))
    workspace = json.dumps(result.get("workspace_snapshot", {}), indent=2)
    return "\n".join(
        [
            "<details>",
            (
                f"<summary><span class=\"{status_class}\">{status}</span> "
                f"{html.escape(result.get('task_id', ''))} "
                f"expected={html.escape(str(result.get('expected', '')))} "
                f"predicted={html.escape(str(result.get('predicted', '')))}</summary>"
            ),
            f"<p class=\"meta\">tool calls: {result.get('tool_calls', 0)} | "
            f"latency: {float(result.get('latency_seconds', 0.0)):.2f}s | "
            f"error: {html.escape(str(result.get('error', '')))}</p>",
            "<h3>Raw answer</h3>",
            f"<pre>{html.escape(str(result.get('raw_answer', '')))}</pre>",
            "<h3>Trace</h3>",
            trace_html,
            "<h3>Workspace snapshot</h3>",
            f"<pre>{html.escape(workspace)}</pre>",
            "</details>",
        ]
    )


def _render_trace_entry(entry: dict[str, Any]) -> str:
    phase = entry.get("phase", "")
    compact = {
        key: value
        for key, value in entry.items()
        if key not in {"workspace_after", "buffer_after", "goals_after"}
    }
    return (
        f"<details><summary>{html.escape(str(phase))}</summary>"
        f"<pre>{html.escape(json.dumps(compact, indent=2))}</pre></details>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render benchmark trace JSON as HTML")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = render_to_file(args.input, args.output)
    print(output)


if __name__ == "__main__":
    main()
