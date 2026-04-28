"""Tests for post-broadcast subscriber bus behavior."""

import time

from gwt_context.application.attention import EvidencePlan
from gwt_context.application.broadcast_bus import (
    BroadcastBus,
    BroadcastContext,
    BroadcastProposal,
    ContradictionCheckerSubscriber,
    ExternalReasoningSubscriber,
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
    assert [decision.reason for decision in result.decisions] == ["accepted", "max_accepted"]
    payload = broadcast_bus_result_to_dict(result)
    assert payload["accepted"][0]["payload"]["query"] == "Paper Beta cites"
    assert payload["summary"]["accepted_count"] == 1
    assert payload["summary"]["inhibited_reasons"] == {"max_accepted": 1}
    assert payload["proposal_groups"]["proposals_by_kind"] == {"query_memory": 2}


def test_broadcast_bus_inhibits_repeated_accepted_proposals() -> None:
    bus = BroadcastBus([RelationContinuationSubscriber()], threshold=0.7)

    first = bus.publish(_context())
    second = bus.publish(_context())

    assert first.accepted[0].payload["query"] == "Paper Beta cites"
    assert second.accepted == ()
    assert second.inhibited[0].payload["query"] == "Paper Beta cites"
    assert second.decisions[0].reason == "below_threshold"


def test_broadcast_bus_inhibits_queries_after_exact_resolution() -> None:
    bus = BroadcastBus([StructuredResolverSubscriber(), RelationContinuationSubscriber()])

    result = bus.publish(_context())

    assert [proposal.kind for proposal in result.accepted] == ["resolve_answer"]
    assert any(proposal.kind == "query_memory" for proposal in result.inhibited)
    assert any(decision.reason == "resolved_answer_present" for decision in result.decisions)


def test_contradiction_checker_requires_configured_markers() -> None:
    context = _context(broadcast_text="Alpha disagrees with Beta")

    assert ContradictionCheckerSubscriber().propose(context) == ()

    proposals = ContradictionCheckerSubscriber(["disagrees with"]).propose(context)
    assert proposals[0].kind == "flag_contradiction"


def test_broadcast_bus_records_subscriber_timeout() -> None:
    class SlowSubscriber:
        name = "slow"

        def propose(self, _context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
            time.sleep(0.02)
            return ()

    result = BroadcastBus(
        [SlowSubscriber()],
        subscriber_timeout_seconds=0.001,
    ).publish(_context())

    assert result.proposals == ()
    assert result.subscriber_reports[0].status == "timeout"


def test_broadcast_bus_opens_circuit_after_repeated_failures() -> None:
    class FailingSubscriber:
        name = "failing"

        def propose(self, _context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
            raise RuntimeError("boom")

    bus = BroadcastBus([FailingSubscriber()], circuit_breaker_failures=1)

    first = bus.publish(_context())
    second = bus.publish(_context())

    assert first.subscriber_reports[0].status == "error"
    assert second.subscriber_reports[0].status == "circuit_open"
    assert bus.settings["failure_counts"] == {"failing": 1}


def test_broadcast_bus_limits_proposals_and_truncates_large_payloads() -> None:
    class NoisySubscriber:
        name = "noisy"

        def propose(self, _context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
            return tuple(
                BroadcastProposal(
                    subscriber=self.name,
                    kind="query_memory",
                    priority=0.9,
                    rationale="noise",
                    payload={"query": "x" * 20},
                )
                for _ in range(3)
            )

    result = BroadcastBus(
        [NoisySubscriber()],
        max_proposals_per_subscriber=2,
        max_payload_chars=10,
    ).publish(_context())

    assert len(result.proposals) == 2
    assert result.proposals[0].payload["truncated"] is True
    assert result.subscriber_reports[0].proposal_count == 2


def test_contradiction_checker_flags_structured_record_conflicts() -> None:
    context = _context(
        question="Is Employee-001 consistent?",
        broadcast_text="Employee-001 status active",
        context_chunks=(
            "Employee-001 | status=active | department=Research",
            "Employee-001 | status=on_leave | department=Research",
        ),
    )

    proposals = ContradictionCheckerSubscriber().propose(context)

    assert proposals[0].kind == "flag_contradiction"
    assert proposals[0].payload["conflicts"][0]["record_id"] == "Employee-001"


def test_external_reasoning_subscriber_sanitizes_injected_proposals() -> None:
    def external(_context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
        return (
            BroadcastProposal(
                subscriber="raw",
                kind="flag_contradiction",
                priority=0.9,
                rationale="nli",
                payload={"label": "contradiction"},
            ),
            BroadcastProposal(
                subscriber="raw",
                kind="unsupported",
                priority=1.0,
                rationale="bad",
            ),
        )

    proposals = ExternalReasoningSubscriber("nli_agent", external).propose(_context())

    assert len(proposals) == 1
    assert proposals[0].subscriber == "nli_agent"
    assert proposals[0].kind == "flag_contradiction"
