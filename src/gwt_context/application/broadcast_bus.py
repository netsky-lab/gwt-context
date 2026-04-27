"""Post-broadcast subscriber bus for GWT-style global availability."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from gwt_context.application.structured import (
    collection_evidence_to_dict,
    resolve_collection_evidence,
    resolve_relation_evidence,
)


@dataclass(frozen=True)
class BroadcastContext:
    """Shared broadcast event visible to independent subscribers."""

    question: str
    broadcast_id: str
    broadcast_text: str
    pass_number: int
    evidence_plan: Any
    context_chunks: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BroadcastProposal:
    """Independent subscriber proposal after reading a broadcast."""

    subscriber: str
    kind: str
    priority: float
    rationale: str
    payload: Mapping[str, Any] = field(default_factory=dict)


class BroadcastSubscriber(Protocol):
    """Processor that independently reacts to a globally broadcast workspace."""

    name: str

    def propose(self, context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
        """Return proposals after reading the current broadcast."""
        ...


@dataclass(frozen=True)
class BroadcastBusResult:
    """Collected and arbitrated proposals for one broadcast event."""

    broadcast_id: str
    proposals: tuple[BroadcastProposal, ...]
    accepted: tuple[BroadcastProposal, ...]


class BroadcastBus:
    """Fan out a broadcast to subscribers and arbitrate their proposals."""

    def __init__(
        self,
        subscribers: Sequence[BroadcastSubscriber],
        *,
        max_accepted: int = 4,
        threshold: float = 0.5,
    ) -> None:
        self._subscribers = tuple(subscribers)
        self._max_accepted = max_accepted
        self._threshold = threshold

    @property
    def subscribers(self) -> tuple[BroadcastSubscriber, ...]:
        """Configured subscribers in call order."""
        return self._subscribers

    def publish(self, context: BroadcastContext) -> BroadcastBusResult:
        """Publish one broadcast event and return arbitrated proposals."""
        proposals: list[BroadcastProposal] = []
        for subscriber in self._subscribers:
            proposals.extend(subscriber.propose(context))
        accepted = _arbitrate(proposals, self._threshold, self._max_accepted)
        return BroadcastBusResult(
            broadcast_id=context.broadcast_id,
            proposals=tuple(proposals),
            accepted=tuple(accepted),
        )


class StructuredResolverSubscriber:
    """Subscriber that tries exact collection/relation resolution from broadcast context."""

    name = "structured_resolver"

    def propose(self, context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
        if not context.context_chunks:
            return ()
        evidence = resolve_collection_evidence(context.question, context.context_chunks)
        if evidence is None:
            evidence = resolve_relation_evidence(context.question, context.context_chunks)
        if evidence is None:
            return ()
        return (
            BroadcastProposal(
                subscriber=self.name,
                kind="resolve_answer",
                priority=0.95,
                rationale="Exact structured evidence matched the broadcast question.",
                payload={"evidence": collection_evidence_to_dict(evidence)},
            ),
        )


class SemanticRecallSubscriber:
    """Subscriber that proposes a follow-up memory query from broadcast entities."""

    name = "semantic_recall"

    def propose(self, context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
        entities = _broadcast_entities(context.broadcast_text)
        if not entities:
            return ()
        query = " ".join([entities[0], *_question_terms(context.question)[:3]])
        return (
            BroadcastProposal(
                subscriber=self.name,
                kind="query_memory",
                priority=0.65,
                rationale="Broadcast exposed an entity that may activate related memory.",
                payload={"query": query},
            ),
        )


class RelationContinuationSubscriber:
    """Subscriber that proposes continuing relation chains exposed by broadcast."""

    name = "relation_continuation"

    def propose(self, context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
        relation = _relation_term(context.question, context.broadcast_text)
        entities = _broadcast_entities(context.broadcast_text)
        if not relation or not entities:
            return ()
        return (
            BroadcastProposal(
                subscriber=self.name,
                kind="query_memory",
                priority=0.78,
                rationale="Broadcast contains a relation chain that may need continuation.",
                payload={"query": f"{entities[-1]} {relation}"},
            ),
        )


class ContradictionCheckerSubscriber:
    """Subscriber that flags obvious contradiction language in the broadcast."""

    name = "contradiction_checker"

    def propose(self, context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
        lowered = context.broadcast_text.lower()
        markers = ("contradiction", "conflict", "disagrees with", "not equal")
        if not any(marker in lowered for marker in markers):
            return ()
        return (
            BroadcastProposal(
                subscriber=self.name,
                kind="flag_contradiction",
                priority=0.85,
                rationale="Broadcast contains explicit contradiction markers.",
                payload={"markers": [marker for marker in markers if marker in lowered]},
            ),
        )


class PlanCriticSubscriber:
    """Subscriber that flags empty broadcasts or missing evidence."""

    name = "plan_critic"

    def propose(self, context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
        if context.broadcast_text.strip():
            return ()
        return (
            BroadcastProposal(
                subscriber=self.name,
                kind="ask_followup",
                priority=0.7,
                rationale="Broadcast is empty; the controller should gather more evidence.",
                payload={"question": context.question},
            ),
        )


def create_default_broadcast_bus() -> BroadcastBus:
    """Create the standard post-broadcast subscriber bus."""
    return BroadcastBus(
        subscribers=[
            StructuredResolverSubscriber(),
            SemanticRecallSubscriber(),
            RelationContinuationSubscriber(),
            ContradictionCheckerSubscriber(),
            PlanCriticSubscriber(),
        ]
    )


def broadcast_bus_result_to_dict(result: BroadcastBusResult) -> dict[str, Any]:
    """Serialize a bus result for traces."""
    return {
        "broadcast_id": result.broadcast_id,
        "proposals": [_proposal_to_dict(proposal) for proposal in result.proposals],
        "accepted": [_proposal_to_dict(proposal) for proposal in result.accepted],
    }


def broadcast_context_to_dict(context: BroadcastContext) -> dict[str, Any]:
    """Serialize a broadcast context for debugging."""
    return {
        "question": context.question,
        "broadcast_id": context.broadcast_id,
        "pass_number": context.pass_number,
        "evidence_plan": _evidence_plan_to_dict(context.evidence_plan),
        "context_count": len(context.context_chunks),
        "metadata": dict(context.metadata),
    }


def _proposal_to_dict(proposal: BroadcastProposal) -> dict[str, Any]:
    return {
        "subscriber": proposal.subscriber,
        "kind": proposal.kind,
        "priority": proposal.priority,
        "rationale": proposal.rationale,
        "payload": dict(proposal.payload),
    }


def _evidence_plan_to_dict(plan: Any) -> dict[str, Any]:
    return {
        "strategy": str(getattr(plan, "strategy", "")),
        "answer": str(getattr(plan, "answer", "")),
        "queries": list(getattr(plan, "queries", ())),
        "evidence": list(getattr(plan, "evidence", ())),
        "metadata": dict(getattr(plan, "metadata", {})),
    }


def _arbitrate(
    proposals: Sequence[BroadcastProposal],
    threshold: float,
    max_accepted: int,
) -> list[BroadcastProposal]:
    accepted: list[BroadcastProposal] = []
    seen_keys: set[tuple[str, str]] = set()
    for proposal in sorted(proposals, key=lambda item: item.priority, reverse=True):
        if proposal.priority < threshold:
            continue
        key = (proposal.kind, str(proposal.payload.get("query") or proposal.payload.get("answer")))
        if key in seen_keys:
            continue
        accepted.append(proposal)
        seen_keys.add(key)
        if len(accepted) >= max_accepted:
            break
    return accepted


def _question_terms(question: str) -> list[str]:
    return [
        token.strip(" ?'\".,").lower()
        for token in question.split()
        if len(token.strip(" ?'\".,")) > 3
    ][:6]


def _broadcast_entities(text: str) -> list[str]:
    pattern = re.compile(r"\b[A-Z][A-Za-z0-9.-]*(?:\s+[A-Z][A-Za-z0-9.-]*){0,4}")
    return _dedupe(match.group(0).strip() for match in pattern.finditer(text))


def _relation_term(question: str, broadcast_text: str) -> str:
    lowered = f"{question}\n{broadcast_text}".lower()
    for relation in ("doctoral advisor", "worked with", "extended", "cites", "reports to"):
        if relation in lowered:
            return relation
    return ""


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
