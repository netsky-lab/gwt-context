"""Tests for reusable attention controller behavior."""

from types import SimpleNamespace
from unittest.mock import Mock

from gwt_context.application.attention import (
    AttentionController,
    EvidencePlan,
    GenericEvidenceResolver,
)
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
