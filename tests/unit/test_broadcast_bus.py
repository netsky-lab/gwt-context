"""Tests for post-broadcast subscriber bus behavior."""

from gwt_context.application.attention import EvidencePlan
from gwt_context.application.broadcast_bus import (
    BroadcastBus,
    BroadcastContext,
    BroadcastProposal,
    RelationContinuationSubscriber,
    SemanticRecallSubscriber,
    StructuredResolverSubscriber,
    broadcast_bus_result_to_dict,
)


def _context(
    *,
    question: str = "What does Paper Alpha cite cite?",
    broadcast_text: str = "Paper Alpha --cites--> Paper Beta",
    context_chunks: tuple[str, ...] = (
        "Paper Alpha -> cites -> Paper Beta",
        "Paper Beta -> cites -> Paper Gamma",
    ),
) -> BroadcastContext:
    return BroadcastContext(
        question=question,
        broadcast_id="bc-1",
        broadcast_text=broadcast_text,
        pass_number=1,
        evidence_plan=EvidencePlan(strategy="test"),
        context_chunks=context_chunks,
    )


def test_structured_resolver_subscriber_proposes_exact_answer() -> None:
    proposals = StructuredResolverSubscriber().propose(_context())

    assert len(proposals) == 1
    assert proposals[0].kind == "resolve_answer"
    assert proposals[0].payload["evidence"]["answer"] == "Paper Gamma"


def test_recall_subscribers_propose_queries_from_shared_broadcast() -> None:
    context = _context()

    semantic = SemanticRecallSubscriber().propose(context)
    relation = RelationContinuationSubscriber().propose(context)

    assert semantic[0].kind == "query_memory"
    assert "Paper Alpha" in semantic[0].payload["query"]
    assert relation[0].payload["query"] == "Paper Beta cites"


def test_broadcast_bus_arbitrates_by_priority_and_threshold() -> None:
    class LowPrioritySubscriber:
        name = "low"

        def propose(self, _context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
            return (
                BroadcastProposal(
                    subscriber=self.name,
                    kind="query_memory",
                    priority=0.1,
                    rationale="too weak",
                    payload={"query": "weak"},
                ),
            )

    bus = BroadcastBus(
        [LowPrioritySubscriber(), RelationContinuationSubscriber()],
        threshold=0.5,
        max_accepted=1,
    )

    result = bus.publish(_context())

    assert len(result.proposals) == 2
    assert len(result.accepted) == 1
    assert result.accepted[0].subscriber == "relation_continuation"
    payload = broadcast_bus_result_to_dict(result)
    assert payload["accepted"][0]["payload"]["query"] == "Paper Beta cites"
