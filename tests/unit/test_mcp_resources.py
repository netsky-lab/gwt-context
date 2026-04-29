"""Unit tests for MCP resource boundary behavior."""

import asyncio
from unittest.mock import Mock

from mcp.server.fastmcp import FastMCP

from gwt_context.application.attention import AttentionRun, AttentionTraceStore, EvidencePlan
from gwt_context.domain.models import ActivationState, MemoryItem, MemoryType
from gwt_context.mcp.resources import register_resources


def _register_resources(
    cycle: object,
    store: object,
    attention_trace: AttentionTraceStore | None = None,
) -> FastMCP:
    mcp = FastMCP("gwt-context-test")
    register_resources(mcp, cycle, store, attention_trace)
    return mcp


def _call_resource(mcp: FastMCP, uri: str, *args: object) -> str:
    async def runner() -> str:
        resource = await mcp._resource_manager.get_resource(uri)
        return resource.fn(*args)  # type: ignore[attr-defined]

    return asyncio.run(runner())


class TestResourceBoundaryDelegation:
    def test_workspace_resource_uses_cycle_workspace_broadcast_api(self):
        cycle = Mock()
        cycle.get_workspace_broadcast = Mock(return_value="=== WORKSPACE ===\nitem-a\n=== END ===")
        store = Mock()

        mcp = _register_resources(cycle, store)
        result = _call_resource(mcp, "gwt://workspace")

        cycle.get_workspace_broadcast.assert_called_once()
        assert result == "=== WORKSPACE ===\nitem-a\n=== END ==="

    def test_workspace_slots_resource_uses_cycle_inspect_workspace_payload(self):
        cycle = Mock()
        cycle.inspect = Mock(
            return_value={
                "items": [
                    {
                        "index": 0,
                        "id": "item-a",
                        "memory_type": "semantic",
                        "activation_level": 0.55,
                        "content": "alpha",
                        "linked_ids": ["item-b"],
                        "empty": False,
                    },
                    {
                        "index": 1,
                        "id": None,
                        "empty": True,
                    },
                ]
            }
        )
        store = Mock()

        mcp = _register_resources(cycle, store)
        result = _call_resource(mcp, "gwt://workspace/slots")

        cycle.inspect.assert_called_with("workspace")
        assert result == (
            "Slot 0: [item-a] (semantic, a=0.55) alpha\n"
            "  Links: item-b\n"
            "Slot 1: [empty]"
        )

    def test_goals_resource_uses_cycle_inspect_goals_payload(self):
        cycle = Mock()
        cycle.inspect = Mock(
            return_value={
                "items": [
                    {
                        "id": "goal-1",
                        "description": "Find apples",
                        "keywords": ["orchard", "fruit"],
                        "priority": 1.2,
                    }
                ]
            }
        )
        store = Mock()

        mcp = _register_resources(cycle, store)
        result = _call_resource(mcp, "gwt://goals")

        cycle.inspect.assert_called_with("goals")
        assert result == "[goal-1] (p=1.2) Find apples\nKeywords: orchard, fruit"

    def test_stats_resource_uses_cycle_inspect_workspace_and_stats_payload(self):
        cycle = Mock()
        cycle.inspect = Mock(
            side_effect=[
                {"occupied_count": 2, "capacity": 7},
                {"total_items": 10, "buffer_size": 3, "broadcasts": 4, "active_goals": 1},
            ]
        )
        store = Mock()

        mcp = _register_resources(cycle, store)
        result = _call_resource(mcp, "gwt://stats")

        assert cycle.inspect.call_count == 2
        assert cycle.inspect.call_args_list[0].args == ("workspace",)
        assert cycle.inspect.call_args_list[1].args == ("stats",)
        assert (
            result
            == "Total items: 10\nWorkspace: 2/7\nBuffer: 3\nBroadcasts: 4\nActive goals: 1"
        )

    def test_health_resource_reports_compact_runtime_status(self):
        cycle = Mock()
        cycle.inspect = Mock(
            side_effect=[
                {"occupied_count": 2, "capacity": 7},
                {"total_items": 10, "buffer_size": 3, "broadcasts": 4, "active_goals": 1},
                {"configured": True},
            ]
        )
        store = Mock()
        store.get_all_items = Mock(return_value=[Mock(), Mock()])

        mcp = _register_resources(cycle, store)
        result = _call_resource(mcp, "gwt://health")

        assert '"status": "ready"' in result
        assert '"persisted_items": 2' in result
        assert '"broadcast_bus_configured": true' in result

    def test_memory_resource_reads_from_store_port(self):
        cycle = Mock()
        cycle.inspect = Mock()
        store = Mock()
        store.get_item = Mock(
            return_value=MemoryItem(
                id="item-1",
                memory_type=MemoryType.SEMANTIC,
                activation_state=ActivationState.LONG_TERM,
                content="A",
                tags=["t1"],
            )
        )

        mcp = _register_resources(cycle, store)
        result = _call_resource(mcp, "gwt://memory/item-1")

        store.get_item.assert_called_once_with("item-1")
        assert "ID: item-1" in result
        assert "State: long_term" in result

    def test_last_attention_resource_reads_trace_store(self):
        cycle = Mock()
        store = Mock()
        attention_trace = AttentionTraceStore()
        attention_trace.record(
            "Find Ada",
            AttentionRun(
                evidence=EvidencePlan(strategy="generic", queries=("Ada",)),
                tool_call_count=3,
                broadcast_text="Ada fact",
                admitted_ids=("item-1",),
                steps=(),
            ),
        )

        mcp = _register_resources(cycle, store, attention_trace)
        result = _call_resource(mcp, "gwt://attention/last")

        assert '"question": "Find Ada"' in result
        assert '"strategy": "generic"' in result
