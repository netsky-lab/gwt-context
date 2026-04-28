"""Real stdio MCP client smoke for the packaged gwt-context server."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import AnyUrl


async def run_stdio_smoke() -> dict[str, Any]:
    """Start `python -m gwt_context` and exercise public MCP protocol calls."""
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        env.update(
            {
                "GWT_DATA_DIR": tmp,
                "GWT_EMBEDDING_PROVIDER": "hash",
                "GWT_EMBEDDING_MODEL": "hash",
                "GWT_EMBEDDING_DIM": "32",
                "GWT_WORKSPACE_CAPACITY": "4",
            }
        )
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "gwt_context"],
            env=env,
            cwd=str(Path.cwd()),
        )
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = {tool.name for tool in tools.tools}
                required_tools = {
                    "gwt_store",
                    "gwt_attend",
                    "gwt_bus_inspect",
                    "gwt_trace_explain",
                    "gwt_inspect",
                }
                missing_tools = sorted(required_tools - tool_names)
                if missing_tools:
                    raise RuntimeError(f"missing MCP tools: {missing_tools}")

                stored = [
                    await _call_json(
                        session,
                        "gwt_store",
                        {"content": "Paper Alpha -> cites -> Paper Beta", "tags": ["stdio"]},
                    ),
                    await _call_json(
                        session,
                        "gwt_store",
                        {"content": "Paper Beta -> cites -> Paper Gamma", "tags": ["stdio"]},
                    ),
                ]
                attended = await _call_json(
                    session,
                    "gwt_attend",
                    {
                        "question": "What does Paper Alpha cite cite?",
                        "planner": "graph",
                        "k": 3,
                        "passes": 1,
                    },
                )
                bus = await _call_json(session, "gwt_bus_inspect", {})
                trace = await _call_json(session, "gwt_trace_explain", {})
                workspace = await _call_json(session, "gwt_inspect", {"target": "workspace"})
                attention_resource = await session.read_resource(AnyUrl("gwt://attention/last"))
                resource_payload = _resource_json(attention_resource)

                answer = str(attended.get("evidence_plan", {}).get("answer", ""))
                if answer != "Paper Gamma":
                    raise RuntimeError(f"unexpected graph answer: {answer!r}")
                if trace.get("status") != "ok":
                    raise RuntimeError(f"unexpected trace status: {trace.get('status')!r}")

                bus_result = bus.get("broadcast_bus", {}).get("last_result", {})
                return {
                    "status": "ok",
                    "server_entrypoint": "python -m gwt_context",
                    "tool_count": len(tool_names),
                    "stored_ids": [str(item.get("id", "")) for item in stored],
                    "answer": answer,
                    "trace_status": trace.get("status", ""),
                    "bus_accepted": len(bus_result.get("accepted", [])),
                    "bus_inhibited": len(bus_result.get("inhibited", [])),
                    "workspace_size": len(workspace.get("items", [])),
                    "attention_resource_answer": resource_payload.get("evidence_plan", {}).get(
                        "answer",
                        "",
                    ),
                }


def _resource_json(result: Any) -> dict[str, Any]:
    contents = getattr(result, "contents", [])
    for content in contents:
        text = getattr(content, "text", None)
        if isinstance(text, str):
            loaded = json.loads(text)
            if isinstance(loaded, dict):
                return loaded
    raise RuntimeError("resource result did not contain JSON text")


async def _call_json(
    session: ClientSession,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    result = await session.call_tool(name, arguments)
    if result.isError:
        raise RuntimeError(f"MCP tool {name} failed: {_first_text(result)}")
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    loaded = json.loads(_first_text(result))
    if not isinstance(loaded, dict):
        raise RuntimeError(f"MCP tool {name} did not return a JSON object")
    return loaded


def _first_text(result: Any) -> str:
    for content in getattr(result, "content", []):
        text = getattr(content, "text", None)
        if isinstance(text, str):
            return text
    raise RuntimeError("MCP result did not contain text")


def main() -> None:
    """Run the stdio smoke and print a compact JSON report."""
    parser = argparse.ArgumentParser(description="Run real stdio MCP smoke")
    parser.add_argument("--compact", action="store_true", help="Print one-line JSON")
    args = parser.parse_args()
    report = asyncio.run(run_stdio_smoke())
    if args.compact:
        print(json.dumps(report, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
