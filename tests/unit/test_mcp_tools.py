"""Unit tests for MCP tool handler boundaries.

These tests ensure handlers stay thin and call application-level APIs
rather than peeking into private/internal service fields.
"""

from unittest.mock import Mock

from mcp.server.fastmcp import FastMCP

from gwt_context.application.attention import AttentionRun, AttentionTraceStore, EvidencePlan
from gwt_context.domain.models import ActivationState, CompetitionResult, MemoryItem, MemoryType
from gwt_context.mcp.tools import register_tools


def _register_tool_cycle_handlers(
    cycle: object,
    ingestion: object,
    attention_trace: object | None = None,
) -> FastMCP:
    mcp = FastMCP("gwt-context-test")
    register_tools(mcp, cycle, ingestion, attention_trace)
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
            tags=["scope:default", "namespace:default"],
        )
        ingestion = Mock()
        ingestion.ingest = Mock(return_value=item)

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        gwt_store = _tool_call(mcp, "gwt_store")

        result = gwt_store("hello world")

        cycle.enqueue_for_competition.assert_called_once_with(item)
        assert result["id"] == "stored-1"
        assert "scope:default" in result["tags"]
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

    def test_gwt_query_validates_input_without_touching_ingestion(self):
        cycle = Mock()
        ingestion = Mock()

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        gwt_query = _tool_call(mcp, "gwt_query")

        empty = gwt_query("", k=1)
        invalid_k = gwt_query("Ada", k=0)
        invalid_type = gwt_query("Ada", memory_type="unknown")

        assert empty["error"] == "query must not be empty"
        assert invalid_k["error"] == "k must be >= 1"
        assert invalid_type["error"] == "unsupported memory_type: unknown"
        ingestion.query_similar.assert_not_called()

    def test_gwt_store_rejects_empty_content_without_ingestion(self):
        cycle = Mock()
        ingestion = Mock()

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        result = _tool_call(mcp, "gwt_store")("   ")

        assert result["error"] == "content must not be empty"
        ingestion.ingest.assert_not_called()

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
            planner="semantic",
            admit=True,
        )

        cycle.set_goal.assert_called_once()
        cycle.enqueue_for_competition.assert_called()
        assert cycle.run.call_count == 2
        assert result["planner"] == "semantic"
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

    def test_gwt_resolve_uses_runtime_structured_memory(self):
        cycle = Mock()
        cycle.enqueue_for_competition = Mock()
        ingestion = Mock()
        ingestion.ingest = Mock(
            side_effect=[
                MemoryItem(
                    id="idea-1",
                    content="Idea-001 | type=twitter | topic=GWT | score=9 | status=ready",
                    memory_type=MemoryType.SEMANTIC,
                    activation_state=ActivationState.PRECONSCIOUS,
                ),
                MemoryItem(
                    id="idea-2",
                    content="Idea-002 | type=twitter | topic=memory | score=7 | status=draft",
                    memory_type=MemoryType.SEMANTIC,
                    activation_state=ActivationState.PRECONSCIOUS,
                ),
            ]
        )
        ingestion.query_similar = Mock(return_value=[])

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        gwt_store = _tool_call(mcp, "gwt_store")
        gwt_store("Idea-001 | type=twitter | topic=GWT | score=9 | status=ready")
        gwt_store("Idea-002 | type=twitter | topic=memory | score=7 | status=draft")

        result = _tool_call(mcp, "gwt_resolve")(
            "How many ideas have status = 'ready'?",
            planner="structured",
        )

        assert result["planner"] == "structured"
        assert result["context_count"] == 2
        assert result["evidence_plan"]["answer"] == "1"
        assert result["evidence_plan"]["strategy"] == "structured_count_status"
        ingestion.query_similar.assert_not_called()

    def test_gwt_collection_query_reads_runtime_collection_index(self):
        cycle = Mock()
        cycle.enqueue_for_competition = Mock()
        ingestion = Mock()
        ingestion.ingest = Mock(
            side_effect=[
                MemoryItem(
                    id="idea-1",
                    content="Idea-001 | type=twitter | topic=GWT | score=9 | status=ready",
                    memory_type=MemoryType.SEMANTIC,
                    activation_state=ActivationState.PRECONSCIOUS,
                ),
                MemoryItem(
                    id="idea-2",
                    content="Idea-002 | type=twitter | topic=memory | score=7 | status=draft",
                    memory_type=MemoryType.SEMANTIC,
                    activation_state=ActivationState.PRECONSCIOUS,
                ),
            ]
        )

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        gwt_store = _tool_call(mcp, "gwt_store")
        gwt_store("Idea-001 | type=twitter | topic=GWT | score=9 | status=ready")
        gwt_store("Idea-002 | type=twitter | topic=memory | score=7 | status=draft")

        top = _tool_call(mcp, "gwt_collection_query")(
            operation="top_k",
            metric="score",
            k=1,
        )
        average = _tool_call(mcp, "gwt_collection_query")(
            operation="average",
            metric="score",
            field="type",
            value="twitter",
        )

        assert top["answer"] == "Idea-001"
        assert top["matched_count"] == 1
        assert average["answer"] == "8.0"

    def test_gwt_collection_query_restores_runtime_index_from_persisted_items(self):
        cycle = Mock()
        ingestion = Mock()
        ingestion.all_items = Mock(
            return_value=[
                MemoryItem(
                    id="idea-1",
                    content="Idea-001 | type=twitter | topic=GWT | score=9 | status=ready",
                    memory_type=MemoryType.SEMANTIC,
                    activation_state=ActivationState.LONG_TERM,
                ),
                MemoryItem(
                    id="idea-2",
                    content="Idea-002 | type=twitter | topic=memory | score=7 | status=draft",
                    memory_type=MemoryType.SEMANTIC,
                    activation_state=ActivationState.LONG_TERM,
                ),
            ]
        )

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        result = _tool_call(mcp, "gwt_collection_query")(
            operation="filter",
            field="status",
            value="ready",
        )

        assert result["answer"] == "Idea-001"
        assert result["matched_count"] == 1

    def test_gwt_memory_profile_reports_namespace_and_counts(self):
        cycle = Mock()
        cycle.inspect = Mock(return_value={"memory_items": 1})
        ingestion = Mock()
        ingestion.all_items = Mock(
            return_value=[
                MemoryItem(
                    id="item-1",
                    content="Idea-001 | type=twitter | topic=GWT | score=9 | status=ready",
                    memory_type=MemoryType.SEMANTIC,
                    source="tool:gwt_store",
                    tags=["scope:default", "namespace:default"],
                )
            ]
        )

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        result = _tool_call(mcp, "gwt_memory_profile")()

        assert result["status"] == "ok"
        assert result["persisted_item_count"] == 1
        assert result["structured_record_count"] == 1
        assert result["counts_by_type"] == {"semantic": 1}
        cycle.inspect.assert_called_once_with(target="stats")

    def test_gwt_reset_runtime_requires_confirmation_and_preserves_persistence(self):
        cycle = Mock()
        cycle.enqueue_for_competition = Mock()
        ingestion = Mock()
        ingestion.ingest = Mock(
            return_value=MemoryItem(
                id="item-1",
                content="Idea-001 | type=twitter | topic=GWT | score=9 | status=ready",
                memory_type=MemoryType.SEMANTIC,
                activation_state=ActivationState.PRECONSCIOUS,
            )
        )

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        _tool_call(mcp, "gwt_store")("Idea-001 | type=twitter | topic=GWT | score=9 | status=ready")
        denied = _tool_call(mcp, "gwt_reset")(scope="runtime")
        reset = _tool_call(mcp, "gwt_reset")(scope="runtime", confirm="RESET_RUNTIME")
        count_after = _tool_call(mcp, "gwt_collection_query")(operation="count")

        assert denied["error"] == "confirmation required"
        assert reset["persistent_memory_deleted"] is False
        assert reset["cleared_runtime_items"] == 1
        assert count_after["answer"] == "0"

    def test_gwt_export_import_memory_jsonl_round_trip(self):
        cycle = Mock()
        cycle.enqueue_for_competition = Mock()
        original = MemoryItem(
            id="item-1",
            content="Imported-001 | type=note | topic=GWT | score=8",
            memory_type=MemoryType.SEMANTIC,
            source="tool:gwt_store",
            tags=["scope:default"],
        )
        imported = MemoryItem(
            id="item-2",
            content=original.content,
            memory_type=MemoryType.SEMANTIC,
            source="tool:gwt_store",
            tags=["scope:default", "namespace:default"],
        )
        ingestion = Mock()
        ingestion.all_items = Mock(return_value=[original])
        ingestion.ingest = Mock(return_value=imported)

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        exported = _tool_call(mcp, "gwt_export_memory")()
        result = _tool_call(mcp, "gwt_import_memory")(exported["jsonl"], admit=True)

        assert exported["format"] == "gwt-memory-jsonl-v1"
        assert exported["item_count"] == 1
        assert result["status"] == "ok"
        assert result["imported_ids"] == ["item-2"]
        cycle.enqueue_for_competition.assert_called_once_with(imported)

    def test_gwt_import_memory_skips_duplicate_records_by_default(self):
        cycle = Mock()
        original = MemoryItem(
            id="item-1",
            content="Imported-001 | type=note | topic=GWT | score=8",
            memory_type=MemoryType.SEMANTIC,
            source="tool:gwt_store",
            tags=["scope:default", "namespace:default"],
        )
        ingestion = Mock()
        ingestion.all_items = Mock(return_value=[original])
        ingestion.ingest = Mock()

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        exported = _tool_call(mcp, "gwt_export_memory")()
        result = _tool_call(mcp, "gwt_import_memory")(exported["jsonl"])

        assert result["imported_count"] == 0
        assert result["skipped_duplicate_count"] == 1
        ingestion.ingest.assert_not_called()

    def test_gwt_reset_persistent_requires_confirmation_and_returns_backup(self):
        cycle = Mock()
        item = MemoryItem(
            id="item-1",
            content="Persistent-001 | status=ready",
            memory_type=MemoryType.SEMANTIC,
            source="tool:gwt_store",
            tags=["scope:default", "namespace:default"],
        )
        ingestion = Mock()
        ingestion.all_items = Mock(return_value=[item])
        ingestion.delete_items = Mock(return_value=1)

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        denied = _tool_call(mcp, "gwt_reset")(scope="persistent")
        reset = _tool_call(mcp, "gwt_reset")(
            scope="persistent",
            confirm="RESET_PERSISTENT",
        )

        assert denied["error"] == "confirmation required"
        assert reset["deleted_count"] == 1
        assert reset["backup"]["item_count"] == 1
        assert "Persistent-001" in reset["backup"]["jsonl"]
        ingestion.delete_items.assert_called_once_with(["item-1"])

    def test_gwt_restore_memory_replace_requires_confirmation(self):
        cycle = Mock()
        existing = MemoryItem(
            id="old-1",
            content="Old-001 | status=stale",
            memory_type=MemoryType.SEMANTIC,
            source="tool:gwt_store",
            tags=["scope:default", "namespace:default"],
        )
        imported = MemoryItem(
            id="new-1",
            content="New-001 | status=ready",
            memory_type=MemoryType.SEMANTIC,
            source="tool:gwt_import_memory",
            tags=["scope:default", "namespace:default"],
        )
        ingestion = Mock()
        ingestion.all_items = Mock(side_effect=[[], [existing], []])
        ingestion.delete_items = Mock(return_value=1)
        ingestion.ingest = Mock(return_value=imported)

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        jsonl = '{"content":"New-001 | status=ready","memory_type":"semantic"}'
        denied = _tool_call(mcp, "gwt_restore_memory")(jsonl, mode="replace")
        restored = _tool_call(mcp, "gwt_restore_memory")(
            jsonl,
            mode="replace",
            confirm="RESTORE_REPLACE",
        )

        assert denied["error"] == "confirmation required"
        assert restored["mode"] == "replace"
        assert restored["deleted_count"] == 1
        assert restored["imported_count"] == 1

    def test_gwt_collection_query_validates_k(self):
        cycle = Mock()
        ingestion = Mock()

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        result = _tool_call(mcp, "gwt_collection_query")(operation="top_k", k=0)

        assert result["error"] == "k must be >= 1"

    def test_gwt_resolve_uses_runtime_relation_graph(self):
        cycle = Mock()
        cycle.enqueue_for_competition = Mock()
        ingestion = Mock()
        ingestion.ingest = Mock(
            side_effect=[
                MemoryItem(
                    id="paper-1",
                    content="Paper Alpha -> cites -> Paper Beta",
                    memory_type=MemoryType.SEMANTIC,
                    activation_state=ActivationState.PRECONSCIOUS,
                ),
                MemoryItem(
                    id="paper-2",
                    content="Paper Beta -> cites -> Paper Gamma",
                    memory_type=MemoryType.SEMANTIC,
                    activation_state=ActivationState.PRECONSCIOUS,
                ),
            ]
        )

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        gwt_store = _tool_call(mcp, "gwt_store")
        gwt_store("Paper Alpha -> cites -> Paper Beta")
        gwt_store("Paper Beta -> cites -> Paper Gamma")

        result = _tool_call(mcp, "gwt_resolve")(
            "What does Paper Alpha cite cite?",
            planner="graph",
        )

        assert result["evidence_plan"]["strategy"] == "relation_graph_cites"
        assert result["evidence_plan"]["answer"] == "Paper Gamma"

    def test_gwt_trace_explain_reads_attention_trace_store(self):
        cycle = Mock()
        ingestion = Mock()
        attention_trace = AttentionTraceStore()
        attention_trace.record(
            "Find Ada",
            AttentionRun(
                evidence=EvidencePlan(
                    strategy="generic_semantic_query_planner",
                    answer="",
                    queries=("Ada",),
                    metadata={"planner": "semantic"},
                ),
                tool_call_count=3,
                broadcast_text="Ada fact",
                admitted_ids=("item-1",),
                steps=(),
            ),
        )

        mcp = _register_tool_cycle_handlers(cycle, ingestion, attention_trace)
        result = _tool_call(mcp, "gwt_trace_explain")()

        assert result["status"] == "ok"
        assert result["planner"] == "semantic"
        assert result["strategy"] == "generic_semantic_query_planner"

    def test_gwt_bus_inspect_delegates_to_cycle_read_model(self):
        cycle = Mock()
        cycle.inspect = Mock(
            return_value={
                "target": "broadcast_bus",
                "configured": True,
                "last_result": {
                    "proposals": [{"subscriber": "s"}],
                    "accepted": [{"subscriber": "s"}],
                    "inhibited": [],
                    "subscriber_reports": [{"subscriber": "s", "status": "ok"}],
                },
            }
        )
        ingestion = Mock()

        mcp = _register_tool_cycle_handlers(cycle, ingestion)
        result = _tool_call(mcp, "gwt_bus_inspect")()

        cycle.inspect.assert_called_once_with(target="broadcast_bus")
        assert result["status"] == "ok"
        assert result["summary"]["accepted_count"] == 1
        assert result["summary"]["subscriber_statuses"] == {"ok": 1}
