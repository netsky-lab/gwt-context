"""Integration coverage for the real stdio MCP client smoke."""

from gwt_context.mcp_client_smoke import run_stdio_smoke


def test_real_stdio_mcp_client_smoke() -> None:
    report = __import__("asyncio").run(run_stdio_smoke())

    assert report["status"] == "ok"
    assert report["answer"] == "Paper Gamma"
    assert report["attention_resource_answer"] == "Paper Gamma"
    assert report["bus_accepted"] >= 1
