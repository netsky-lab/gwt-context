"""Tests for reusable attention controller behavior."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from gwt_context.application.attention import (
    AttentionController,
    EvidencePlan,
    GenericEvidenceResolver,
)
from gwt_context.application.broadcast_bus import BroadcastBus, BroadcastProposal
from gwt_context.domain.models import Goal, MemoryItem


class StaticResolver:
    def resolve(self, question, context_chunks, metadata):  # type: ignore[no-untyped-def]
        assert question == "Who advises Ada?"
        assert list(context_chunks) == ["Ada -> Grace"]
        assert metadata == {"kind": "chain"}
        return EvidencePlan(
            strategy="static",
            answer="Grace Hopper",
            queries=("Ada advisor",),
            evidence=("Ada -> Grace",),
        )


def test_attention_controller_sets_goal_admits_queries_and_broadcasts() -> None:
    cycle = Mock()
    cycle.set_goal = Mock(return_value=Goal(id="goal-1", description="Who advises Ada?"))
    cycle.enqueue_for_competition = Mock()
    cycle.run = Mock(
        return_value=SimpleNamespace(
            id="broadcast-1",
            formatted_content="Ada -> Grace",
            admitted_ids=["item-1"],
            evicted_ids=[],
        )
    )
    item = MemoryItem(id="item-1", content="Ada -> Grace")
    ingestion = Mock()
    ingestion.query_similar = Mock(return_value=[item])

    controller = AttentionController(cycle, ingestion, [StaticResolver()], query_k=7)
    result = controller.run(
        "Who advises Ada?",
        ["Ada -> Grace"],
        {"kind": "chain"},
        keywords=["Ada", "advisor"],
    )

    cycle.set_goal.assert_called_once_with(
        description="Who advises Ada?",
        keywords=["Ada", "advisor"],
    )
    ingestion.query_similar.assert_called_once_with(query="Ada advisor", k=7)
    cycle.enqueue_for_competition.assert_called_once_with(item)
    cycle.run.assert_called_once()
    assert result.evidence.answer == "Grace Hopper"
    assert result.tool_call_count == 3
    assert [step.name for step in result.steps] == [
        "gwt_set_goal",
        "evidence_plan",
        "gwt_query",
        "gwt_broadcast",
    ]
    assert result.pass_count == 1


def test_attention_controller_can_run_second_pass_from_broadcast_entities() -> None:
    cycle = Mock()
    cycle.set_goal = Mock(
        return_value=Goal(id="goal-1", description="Who was Ada's doctoral advisor?")
    )
    cycle.enqueue_for_competition = Mock()
    cycle.run = Mock(
        side_effect=[
            SimpleNamespace(
                id="broadcast-1",
                formatted_content=(
                    "Ada Lovelace's doctoral advisor was Grace Hopper at MIT"
                ),
                admitted_ids=["item-1"],
                evicted_ids=[],
            ),
            SimpleNamespace(
                id="broadcast-2",
                formatted_content=(
                    "Grace Hopper's doctoral advisor was Alan Turing at Cambridge"
                ),
                admitted_ids=["item-2"],
                evicted_ids=[],
            ),
        ]
    )
    item_1 = MemoryItem(id="item-1", content="Ada -> Grace")
    item_2 = MemoryItem(id="item-2", content="Grace -> Alan")
    ingestion = Mock()
    ingestion.query_similar = Mock(side_effect=[[item_1], [item_2], [], [], []])

    controller = AttentionController(
        cycle,
        ingestion,
        [
            StaticResolver(),
        ],
        query_k=2,
    )
    result = controller.run(
        "Who advises Ada?",
        ["Ada -> Grace"],
        {"kind": "chain"},
        passes=2,
    )

    queries = [call.kwargs["query"] for call in ingestion.query_similar.call_args_list]
    assert "Grace Hopper related evidence" in queries
    assert cycle.run.call_count == 2
    assert result.pass_count == 2
    assert result.tool_call_count == 8


def test_attention_controller_falls_back_to_question_query() -> None:
    cycle = Mock()
    cycle.set_goal = Mock(return_value=Goal(id="goal-1", description="Q"))
    cycle.enqueue_for_competition = Mock()
    cycle.run = Mock(
        return_value=SimpleNamespace(
            id="broadcast-1",
            formatted_content="",
            admitted_ids=[],
            evicted_ids=[],
        )
    )
    ingestion = Mock()
    ingestion.query_similar = Mock(return_value=[])

    result = AttentionController(cycle, ingestion).run("Q")

    ingestion.query_similar.assert_called_once_with(query="Q", k=10)
    assert result.evidence.strategy == "fallback"
    assert result.tool_call_count == 3


def test_attention_controller_rejects_invalid_pass_count() -> None:
    cycle = Mock()
    ingestion = Mock()

    with pytest.raises(ValueError, match="passes"):
        AttentionController(cycle, ingestion).run("Q", passes=0)


def test_generic_evidence_resolver_plans_question_queries() -> None:
    plan = GenericEvidenceResolver(max_queries=3).resolve(
        "Who advised 'Ada Lovelace' at MIT?",
        [],
        {},
    )

    assert plan.strategy == "generic_semantic_query_planner"
    assert plan.queries[0] == "Who advised 'Ada Lovelace' at MIT?"
    assert "Ada Lovelace" in plan.queries
    assert len(plan.queries) == 3


def test_generic_evidence_resolver_plans_structured_aggregation_queries() -> None:
    plan = GenericEvidenceResolver(max_queries=6).resolve(
        "What is the average years of experience for employees in the Data Science "
        "department? Round to one decimal place.",
        [],
        {"department": "Data Science", "task_type": "aggregate"},
    )

    assert "Data Science department" in plan.queries
    assert "Data Science department years experience" in plan.queries


def test_generic_evidence_resolver_plans_field_target_queries() -> None:
    plan = GenericEvidenceResolver(max_queries=6).resolve(
        "How many employees have status = 'on_leave'? Give just the number.",
        [],
        {},
    )

    assert "employees status on_leave" in plan.queries
    assert "Status: on_leave" in plan.queries


def test_generic_evidence_resolver_returns_exact_employee_top_k_plan() -> None:
    records = [
        _employee_record("Employee-002", score="4.9"),
        _employee_record("Employee-001", score="4.9"),
        _employee_record("Employee-003", score="4.4"),
    ]

    plan = GenericEvidenceResolver().resolve(
        "Who are the top 2 employees by performance score? List their names in order "
        "from highest to lowest, separated by commas.",
        records,
        {},
    )

    assert plan.strategy == "structured_top_k_performance_score"
    assert plan.answer == "Employee-001, Employee-002"
    assert plan.metadata["deterministic_answer"] is True
    assert "workspace_summary" in plan.metadata


def test_generic_evidence_resolver_respects_semantic_planner_mode() -> None:
    records = [
        _employee_record("Employee-002", score="4.9"),
        _employee_record("Employee-001", score="4.9"),
    ]

    plan = GenericEvidenceResolver(planner="semantic").resolve(
        "Who are the top 2 employees by performance score?",
        records,
        {},
    )

    assert plan.strategy == "generic_semantic_query_planner"
    assert plan.answer == ""
    assert plan.metadata["planner"] == "semantic"


def test_generic_evidence_resolver_returns_relation_graph_plan() -> None:
    plan = GenericEvidenceResolver(planner="graph").resolve(
        "Who was Ada Lovelace's doctoral advisor's doctoral advisor?",
        [
            "Ada Lovelace's doctoral advisor was Grace Hopper at MIT",
            "Grace Hopper's doctoral advisor was Alan Turing at Cambridge",
        ],
        {},
    )

    assert plan.strategy == "relation_graph_doctoral_advisor"
    assert plan.answer == "Alan Turing"
    assert plan.metadata["deterministic_answer"] is True
    assert plan.metadata["hops"] == 2


def test_attention_controller_admits_compressed_collection_evidence() -> None:
    cycle = Mock()
    cycle.set_goal = Mock(return_value=Goal(id="goal-1", description="Q"))
    cycle.enqueue_for_competition = Mock()
    cycle.run = Mock(
        return_value=SimpleNamespace(
            id="broadcast-1",
            formatted_content="collection summary",
            admitted_ids=["summary-1"],
            evicted_ids=[],
        )
    )
    summary_item = MemoryItem(id="summary-1", content="summary")
    ingestion = Mock()
    ingestion.ingest = Mock(return_value=summary_item)
    ingestion.query_similar = Mock(return_value=[])
    records = [
        _employee_record("Employee-001", department="Research", years="5"),
        _employee_record("Employee-002", department="Research", years="15"),
    ]

    result = AttentionController(
        cycle,
        ingestion,
        [GenericEvidenceResolver()],
    ).run(
        "What is the average years of experience for employees in the Research "
        "department? Round to one decimal place.",
        records,
    )

    assert result.evidence.answer == "10.0"
    ingestion.ingest.assert_called_once()
    ingestion.query_similar.assert_not_called()
    cycle.enqueue_for_competition.assert_called_once_with(summary_item)
    cycle.run.assert_called_once()
    assert result.tool_call_count == 3


def test_attention_controller_runs_broadcast_subscribers_after_broadcast() -> None:
    cycle = Mock()
    cycle.set_goal = Mock(return_value=Goal(id="goal-1", description="Q"))
    cycle.enqueue_for_competition = Mock()
    cycle.run = Mock(
        return_value=SimpleNamespace(
            id="broadcast-1",
            formatted_content="Paper Alpha --cites--> Paper Beta",
            admitted_ids=["item-1"],
            evicted_ids=[],
        )
    )
    item = MemoryItem(id="item-2", content="Paper Beta -> cites -> Paper Gamma")
    ingestion = Mock()

    def query_similar(*, query: str, k: int):  # type: ignore[no-untyped-def]
        if query == "Paper Beta cites":
            return [item]
        return []

    ingestion.query_similar = Mock(side_effect=query_similar)

    class QuerySubscriber:
        name = "query"

        def propose(self, _context):  # type: ignore[no-untyped-def]
            return (
                BroadcastProposal(
                    subscriber=self.name,
                    kind="query_memory",
                    priority=0.9,
                    rationale="continue chain",
                    payload={"query": "Paper Beta cites"},
                ),
            )

    result = AttentionController(
        cycle,
        ingestion,
        [GenericEvidenceResolver(planner="semantic")],
        broadcast_bus=BroadcastBus([QuerySubscriber()]),
    ).run("What does Paper Alpha cite cite?", passes=1)

    ingestion.query_similar.assert_any_call(query="Paper Beta cites", k=10)
    cycle.enqueue_for_competition.assert_called_once_with(item)
    assert "broadcast_subscribers" in [step.name for step in result.steps]
    assert "subscriber_query" in [step.name for step in result.steps]


def test_attention_controller_applies_resolve_answer_proposal() -> None:
    cycle = Mock()
    cycle.set_goal = Mock(return_value=Goal(id="goal-1", description="Q"))
    cycle.enqueue_for_competition = Mock()
    cycle.run = Mock(
        return_value=SimpleNamespace(
            id="broadcast-1",
            formatted_content="collection summary",
            admitted_ids=[],
            evicted_ids=[],
        )
    )
    ingestion = Mock()
    ingestion.query_similar = Mock(return_value=[])

    class ResolveSubscriber:
        name = "resolve"

        def propose(self, _context):  # type: ignore[no-untyped-def]
            return (
                BroadcastProposal(
                    subscriber=self.name,
                    kind="resolve_answer",
                    priority=0.95,
                    rationale="exact",
                    payload={
                        "evidence": {
                            "answer": "42",
                            "supporting_evidence": ["answer=42"],
                        }
                    },
                ),
            )

    result = AttentionController(
        cycle,
        ingestion,
        broadcast_bus=BroadcastBus([ResolveSubscriber()]),
    ).run("Q")

    assert result.evidence.answer == "42"
    assert result.evidence.metadata["deterministic_answer"] is True
    assert "subscriber_resolve" in [step.name for step in result.steps]


def _employee_record(
    name: str,
    *,
    department: str = "Engineering",
    location: str = "Berlin",
    status: str = "active",
    years: str = "7",
    project: str = "Atlas",
    score: str = "3.5",
) -> str:
    return (
        f"{name} works in the {department} department, based in {location}. "
        f"Status: {status}. They have {years} years of experience and are currently "
        f"assigned to Project {project}. Skills: Python. Performance score: "
        f"{score}/5.0. Salary band: L4."
    )
