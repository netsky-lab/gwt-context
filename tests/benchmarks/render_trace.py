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
            "table{border-collapse:collapse;width:100%;margin:8px 0}",
            "td,th{border:1px solid #ddd;padding:6px;text-align:left}",
            ".ok{color:#177245}.bad{color:#b42318}.meta{color:#555}",
            ".badge{display:inline-block;border:1px solid #ccc;border-radius:999px;"
            "padding:2px 8px;margin:2px;font-size:12px;background:#fff}",
            ".badge-ok{border-color:#9ad3aa;background:#edf8f0;color:#17633a}",
            ".badge-warn{border-color:#f6c56f;background:#fff7e6;color:#8a5200}",
            ".badge-bad{border-color:#f0a0a0;background:#fff0f0;color:#9d1c1c}",
            ".timeline{margin:10px 0}",
            ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}",
            ".mini{border:1px solid #eee;border-radius:6px;padding:8px;background:#fcfcfc}",
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
    trace = result.get("trace", [])
    trace_html = "\n".join(_render_trace_entry(entry) for entry in trace)
    timeline_html = _render_timeline(trace)
    bus_html = _render_bus_summary(result)
    trace_summary = _render_trace_summary(trace)
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
            trace_summary,
            timeline_html,
            bus_html,
            _render_workspace_changes(trace),
            trace_html,
            "<h3>Workspace snapshot</h3>",
            f"<pre>{html.escape(workspace)}</pre>",
            "</details>",
        ]
    )


def _render_bus_summary(result: dict[str, Any]) -> str:
    proposals = accepted = inhibited = actions = policy_skips = 0
    reports: list[dict[str, Any]] = []
    for entry in result.get("trace", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("phase") == "broadcast_bus":
            payload = _entry_payload(entry)
            if isinstance(payload, dict):
                proposals += len(payload.get("proposals", []))
                accepted += len(payload.get("accepted", []))
                inhibited += len(payload.get("inhibited", []))
                reports.extend(
                    report for report in payload.get("subscriber_reports", [])
                    if isinstance(report, dict)
                )
        if entry.get("phase") == "broadcast_bus_tool":
            actions += 1
        if entry.get("phase") == "subscriber_policy_skip":
            policy_skips += 1
    if proposals == accepted == inhibited == actions == policy_skips == 0 and not reports:
        return ""
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(report.get('subscriber', '')))}</td>"
        f"<td>{_status_badge(str(report.get('status', '')))}</td>"
        f"<td>{html.escape(str(report.get('proposal_count', '')))}</td>"
        f"<td>{html.escape(str(report.get('elapsed_ms', '')))}</td>"
        "</tr>"
        for report in reports
    )
    return "\n".join(
        [
            "<h3>Broadcast Bus</h3>",
            (
                f"<p class=\"meta\">proposals={proposals} accepted={accepted} "
                f"inhibited={inhibited} actions={actions} policy_skips={policy_skips}</p>"
            ),
            "<table><thead><tr><th>Subscriber</th><th>Status</th><th>Proposals</th>"
            "<th>ms</th></tr></thead><tbody>",
            rows,
            "</tbody></table>",
            _render_bus_proposal_groups(result),
            _render_inhibited_proposals(result),
        ]
    )


def _render_trace_summary(trace: Any) -> str:
    if not isinstance(trace, list):
        return ""
    phases: dict[str, int] = {}
    for entry in trace:
        if not isinstance(entry, dict):
            continue
        phase = str(entry.get("phase", ""))
        if not phase:
            continue
        phases[phase] = phases.get(phase, 0) + 1
    if not phases:
        return ""
    badges = "".join(
        f"<span class=\"badge\">{html.escape(phase)} x{count}</span>"
        for phase, count in sorted(phases.items())
    )
    return f"<p class=\"meta\">Trace phases: {badges}</p>"


def _render_timeline(trace: Any) -> str:
    if not isinstance(trace, list):
        return ""
    badges = []
    for entry in trace:
        if not isinstance(entry, dict):
            continue
        phase = str(entry.get("phase", ""))
        if not phase:
            continue
        badges.append(
            f"<span class=\"badge {_phase_badge_class(phase)}\">{html.escape(phase)}</span>"
        )
    if not badges:
        return ""
    return f"<div class=\"timeline\">{''.join(badges)}</div>"


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


def _render_bus_proposal_groups(result: dict[str, Any]) -> str:
    grouped: dict[tuple[str, str], dict[str, int]] = {}
    for payload in _bus_payloads(result):
        for state in ("proposals", "accepted", "inhibited"):
            proposals = payload.get(state, [])
            if not isinstance(proposals, list):
                continue
            for proposal in proposals:
                if not isinstance(proposal, dict):
                    continue
                key = (
                    str(proposal.get("subscriber", "")),
                    str(proposal.get("kind", "")),
                )
                counts = grouped.setdefault(key, {"proposals": 0, "accepted": 0, "inhibited": 0})
                counts[state] += 1
    if not grouped:
        return ""
    cards = []
    for (subscriber, kind), counts in sorted(grouped.items()):
        cards.append(
            "<div class=\"mini\">"
            f"<strong>{html.escape(subscriber)} / {html.escape(kind)}</strong><br>"
            f"proposals={counts['proposals']} accepted={counts['accepted']} "
            f"inhibited={counts['inhibited']}"
            "</div>"
        )
    return "<h4>Proposal Groups</h4><div class=\"grid\">" + "".join(cards) + "</div>"


def _render_inhibited_proposals(result: dict[str, Any]) -> str:
    rows = []
    for payload in _bus_payloads(result):
        inhibited = payload.get("inhibited", [])
        if not isinstance(inhibited, list):
            continue
        for proposal in inhibited:
            if not isinstance(proposal, dict):
                continue
            proposal_payload = proposal.get("payload", {})
            if not isinstance(proposal_payload, dict):
                proposal_payload = {}
            reason = proposal.get("rationale", "")
            key = proposal_payload.get("query") or proposal_payload.get("question") or ""
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(proposal.get('subscriber', '')))}</td>"
                f"<td>{html.escape(str(proposal.get('kind', '')))}</td>"
                f"<td>{html.escape(str(key))}</td>"
                f"<td>{html.escape(str(reason))}</td>"
                "</tr>"
            )
    if not rows:
        return ""
    return (
        "<h4>Inhibited Proposals</h4>"
        "<table><thead><tr><th>Subscriber</th><th>Kind</th><th>Key</th>"
        "<th>Rationale</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_workspace_changes(trace: Any) -> str:
    if not isinstance(trace, list):
        return ""
    rows = []
    for entry in trace:
        if not isinstance(entry, dict):
            continue
        workspace = entry.get("workspace_after")
        if not isinstance(workspace, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(entry.get('phase', '')))}</td>"
            f"<td>{html.escape(str(workspace.get('occupied_count', '')))}</td>"
            f"<td>{html.escape(_workspace_preview(workspace))}</td>"
            "</tr>"
        )
    if not rows:
        return ""
    return (
        "<h3>Workspace Changes</h3>"
        "<table><thead><tr><th>Phase</th><th>Occupied</th><th>Top Items</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _bus_payloads(result: dict[str, Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for entry in result.get("trace", []):
        if not isinstance(entry, dict) or entry.get("phase") != "broadcast_bus":
            continue
        payload = _entry_payload(entry)
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _entry_payload(entry: dict[str, Any]) -> Any:
    result = entry.get("result")
    if isinstance(result, dict):
        return result
    return entry.get("payload", {})


def _workspace_preview(workspace: dict[str, Any]) -> str:
    items = workspace.get("items", [])
    if not isinstance(items, list):
        return ""
    previews = []
    for item in items[:3]:
        if not isinstance(item, dict) or item.get("empty"):
            continue
        content = " ".join(str(item.get("content", "")).split())
        previews.append(content[:80])
    return " | ".join(previews)


def _status_badge(status: str) -> str:
    css_class = "badge-ok" if status == "ok" else "badge-bad"
    return f"<span class=\"badge {css_class}\">{html.escape(status)}</span>"


def _phase_badge_class(phase: str) -> str:
    if phase in {"broadcast_bus", "broadcast_bus_tool"}:
        return "badge-ok"
    if phase == "subscriber_policy_skip":
        return "badge-warn"
    if "error" in phase:
        return "badge-bad"
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Render benchmark trace JSON as HTML")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = render_to_file(args.input, args.output)
    print(output)


if __name__ == "__main__":
    main()
