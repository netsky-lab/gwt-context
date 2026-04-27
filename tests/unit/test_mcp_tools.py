"""Unit tests for MCP tool handler boundaries.

These tests ensure handlers stay thin and call application-level APIs
rather than peeking into private/internal service fields.
"""

from unittest.mock import Mock

from mcp.server.fastmcp import FastMCP

from gwt_context.domain.models import ActivationState, CompetitionResult, MemoryItem, MemoryType
from gwt_context.mcp.tools import register_tools


def _register_tool_cycle_handlers(cycle: object, ingestion: object) -> FastMCP:
    mcp = FastMCP("gwt-context-test")
    register_tools(mcp, cycle, ingestion)
    return mcp


def _tool_call(mcp: FastMCP, name: str):
    return mcp._tool_manager.get_tool(name).fn


class TestBoundaryDelegation:
    def test_gwt_compete_delegates_to_application_dry_run(self):
        """MCP dry-run should delegate to the cycle API and not private internals."""
        cycle = Mock()
        cycle.run_competition_dry = Mock(
            return_value=CompetitionResult(winners=[], evicted=[], scores={})
        )
        ingestion = Mock()

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        gwt_compete = _tool_call(mcp, "gwt_compete")

        result = gwt_compete(n_slots=2)

        cycle.run_competition_dry.assert_called_once_with(n_slots=2)
        assert result["winners"] == []
        assert result["would_evict"] == []

    def test_gwt_link_delegates_to_cycle_link_items(self):
        """MCP linking should call cycle.link_items() only."""
        cycle = Mock()
        cycle.link_items = Mock(return_value={"status": "linked", "message": "ok"})
        ingestion = Mock()

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        gwt_link = _tool_call(mcp, "gwt_link")

        result = gwt_link("item-a", "item-b")

        cycle.link_items.assert_called_once_with(source_id="item-a", target_id="item-b")
        assert result["status"] == "linked"

    def test_gwt_evict_delegates_to_cycle_evict_workspace_item(self):
        """MCP eviction should not manipulate workspace/buffer directly."""
        cycle = Mock()
        cycle.evict_workspace_item = Mock(
            return_value={
                "status": "evicted",
                "id": "item-1",
                "message": "Item moved to preconscious buffer",
            }
        )
        ingestion = Mock()

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        gwt_evict = _tool_call(mcp, "gwt_evict")

        result = gwt_evict("item-1")

        cycle.evict_workspace_item.assert_called_once_with(item_id="item-1")
        assert result["status"] == "evicted"

    def test_gwt_store_pushes_to_cycle_buffer_api(self):
        """Store handler should push ingested item through cycle.enqueue_for_competition()."""
        cycle = Mock()
        cycle.enqueue_for_competition = Mock()

        item = MemoryItem(
            id="stored-1",
            memory_type=MemoryType.SEMANTIC,
            activation_state=ActivationState.PRECONSCIOUS,
            linked_ids=[],
        )
        ingestion = Mock()
        ingestion.ingest = Mock(return_value=item)

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        gwt_store = _tool_call(mcp, "gwt_store")

        result = gwt_store("hello world")

        cycle.enqueue_for_competition.assert_called_once_with(item)
        assert result["id"] == "stored-1"
        assert result["status"] == "stored and ready for competition"

    def test_gwt_inspect_delegates_to_cycle_inspect(self):
        """Inspect handler should delegate to cycle.inspect() and remain target-based."""
        cycle = Mock()
        cycle.inspect = Mock(return_value={"status": "ok"})
        ingestion = Mock()

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        gwt_inspect = _tool_call(mcp, "gwt_inspect")

        result = gwt_inspect("stats")

        cycle.inspect.assert_called_once_with(target="stats")
        assert result["status"] == "ok"

    def test_gwt_query_can_admit_results_through_cycle_api(self):
        """Query admission should use the public cycle enqueue API."""
        item = MemoryItem(
            id="item-1",
            content="Ada fact",
            memory_type=MemoryType.SEMANTIC,
            activation_state=ActivationState.LONG_TERM,
        )
        cycle = Mock()
        cycle.enqueue_for_competition = Mock()
        ingestion = Mock()
        ingestion.query_similar = Mock(return_value=[item])

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        result = _tool_call(mcp, "gwt_query")("Ada", admit=True)

        cycle.enqueue_for_competition.assert_called_once_with(item)
        assert result[0]["admitted"] is True

    def test_gwt_attend_runs_application_attention_controller(self):
        """Attend should orchestrate through public cycle and ingestion APIs."""
        item = MemoryItem(
            id="item-1",
            content="Ada Lovelace's doctoral advisor was Grace Hopper",
            memory_type=MemoryType.SEMANTIC,
            activation_state=ActivationState.PRECONSCIOUS,
        )
        cycle = Mock()
        cycle.set_goal = Mock(return_value=Mock(id="goal-1", description="Find Ada", keywords=[]))
        cycle.enqueue_for_competition = Mock()
        cycle.run = Mock(
            side_effect=[
                Mock(
                    id="broadcast-1",
                    formatted_content="Ada Lovelace's doctoral advisor was Grace Hopper at MIT",
                    admitted_ids=["item-1"],
                    evicted_ids=[],
                ),
                Mock(
                    id="broadcast-2",
                    formatted_content="Grace Hopper's doctoral advisor was Alan Turing",
                    admitted_ids=["item-1"],
                    evicted_ids=[],
                ),
            ]
        )
        cycle.inspect = Mock(return_value={"target": "workspace", "items": []})
        ingestion = Mock()
        ingestion.query_similar = Mock(return_value=[item])

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        result = _tool_call(mcp, "gwt_attend")(
            "Find Ada Lovelace's doctoral advisor",
            passes=2,
            planner="generic",
            admit=True,
        )

        cycle.set_goal.assert_called_once()
        cycle.enqueue_for_competition.assert_called()
        assert cycle.run.call_count == 2
        assert result["planner"] == "generic"
        assert result["passes_completed"] == 2
        assert result["admit"] is True
        assert result["evidence_plan"]["strategy"] == "generic_semantic_query_planner"
        assert "Alan Turing" in result["broadcast"]

    def test_gwt_attend_rejects_unsupported_planner(self):
        cycle = Mock()
        ingestion = Mock()

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        result = _tool_call(mcp, "gwt_attend")("Q", planner="benchmark")

        assert result["error"] == "unsupported planner: benchmark"
