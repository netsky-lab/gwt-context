"""Local readiness smoke for the MCP tool surface."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from gwt_context.infrastructure.config import GWTConfig
from gwt_context.server import create_server


def run_smoke() -> dict[str, Any]:
    """Run a local MCP tool workflow without external model downloads."""
    with tempfile.TemporaryDirectory() as tmp:
        config = GWTConfig(
            data_dir=tmp,
            embedding_provider="hash",
            embedding_model="hash",
            embedding_dim=32,
            workspace_capacity=3,
        )
        mcp = create_server(config)
        gwt_store = _tool_call(mcp, "gwt_store")
        gwt_resolve = _tool_call(mcp, "gwt_resolve")
        gwt_attend = _tool_call(mcp, "gwt_attend")
        gwt_trace_explain = _tool_call(mcp, "gwt_trace_explain")
        gwt_inspect = _tool_call(mcp, "gwt_inspect")

        stored = [
            gwt_store("Paper Alpha -> cites -> Paper Beta", tags=["smoke"]),
            gwt_store("Paper Beta -> cites -> Paper Gamma", tags=["smoke"]),
            gwt_store("Idea-001 | type=twitter | topic=GWT | score=9 | status=ready"),
        ]
        resolved = gwt_resolve("What does Paper Alpha cite cite?", planner="graph")
        attended = gwt_attend(
            "What does Paper Alpha cite cite?",
            planner="graph",
            k=3,
            passes=1,
        )
        trace = gwt_trace_explain()
        stats = gwt_inspect("stats")

        return {
            "data_dir": str(Path(tmp)),
            "stored_count": len(stored),
            "resolve_answer": resolved["evidence_plan"]["answer"],
            "attend_strategy": attended["evidence_plan"]["strategy"],
            "trace_status": trace["status"],
            "stats": stats,
        }


def _tool_call(mcp: Any, name: str) -> Any:
    return mcp._tool_manager.get_tool(name).fn


def main() -> None:
    """Print a compact JSON readiness report."""
    print(json.dumps(run_smoke(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
