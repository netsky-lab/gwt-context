"""Post-broadcast subscriber bus for GWT-style global availability."""

from __future__ import annotations

import re
import time
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from gwt_context.application.structured import (
    collection_evidence_to_dict,
    parse_record,
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


@dataclass(frozen=True)
class SubscriberReport:
    """Execution report for one independent subscriber loop."""

    subscriber: str
    status: str
    proposal_count: int = 0
    elapsed_ms: float = 0.0
    error: str = ""


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
    inhibited: tuple[BroadcastProposal, ...] = ()
    subscriber_reports: tuple[SubscriberReport, ...] = ()


class BroadcastBus:
    """Fan out a broadcast to subscribers and arbitrate their proposals."""

    def __init__(
        self,
        subscribers: Sequence[BroadcastSubscriber],
        *,
        max_accepted: int = 4,
        threshold: float = 0.5,
        repetition_penalty: float = 0.2,
        subscriber_timeout_seconds: float = 0.25,
    ) -> None:
        self._subscribers = tuple(subscribers)
        self._max_accepted = max_accepted
        self._threshold = threshold
        self._repetition_penalty = repetition_penalty
        self._subscriber_timeout_seconds = subscriber_timeout_seconds
        self._accepted_counts: dict[tuple[str, str], int] = {}

    @property
    def subscribers(self) -> tuple[BroadcastSubscriber, ...]:
        """Configured subscribers in call order."""
        return self._subscribers

    def publish(self, context: BroadcastContext) -> BroadcastBusResult:
        """Publish one broadcast event and return arbitrated proposals."""
        proposals, reports = self._collect_proposals(context)
        accepted, inhibited = self._arbitrate(proposals)
        for proposal in accepted:
            key = _proposal_key(proposal)
            self._accepted_counts[key] = self._accepted_counts.get(key, 0) + 1
        return BroadcastBusResult(
            broadcast_id=context.broadcast_id,
            proposals=tuple(proposals),
            accepted=tuple(accepted),
            inhibited=tuple(inhibited),
            subscriber_reports=tuple(reports),
        )

    def _collect_proposals(
        self,
        context: BroadcastContext,
    ) -> tuple[list[BroadcastProposal], list[SubscriberReport]]:
        proposals: list[BroadcastProposal] = []
        reports: list[SubscriberReport] = []
        for subscriber in self._subscribers:
            started = time.perf_counter()
            executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix=f"gwt-{subscriber.name}",
            )
            future = executor.submit(subscriber.propose, context)
            try:
                subscriber_proposals = future.result(timeout=self._subscriber_timeout_seconds)
            except TimeoutError:
                future.cancel()
                reports.append(
                    SubscriberReport(
                        subscriber=subscriber.name,
                        status="timeout",
                        elapsed_ms=_elapsed_ms(started),
                    )
                )
            except Exception as exc:
                reports.append(
                    SubscriberReport(
                        subscriber=subscriber.name,
                        status="error",
                        elapsed_ms=_elapsed_ms(started),
                        error=str(exc),
                    )
                )
            else:
                proposals.extend(subscriber_proposals)
                reports.append(
                    SubscriberReport(
                        subscriber=subscriber.name,
                        status="ok",
                        proposal_count=len(subscriber_proposals),
                        elapsed_ms=_elapsed_ms(started),
                    )
                )
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        return proposals, reports

    def _arbitrate(
        self,
        proposals: Sequence[BroadcastProposal],
    ) -> tuple[list[BroadcastProposal], list[BroadcastProposal]]:
        accepted: list[BroadcastProposal] = []
        inhibited: list[BroadcastProposal] = []
        seen_keys: set[tuple[str, str]] = set()
        adjusted = [self._apply_repetition_inhibition(proposal) for proposal in proposals]
        for proposal in sorted(adjusted, key=lambda item: item.priority, reverse=True):
            key = _proposal_key(proposal)
            if proposal.kind == "query_memory" and _has_resolved_answer(accepted):
                inhibited.append(proposal)
                continue
            if proposal.priority < self._threshold:
                inhibited.append(proposal)
                continue
            if key in seen_keys:
                inhibited.append(proposal)
                continue
            accepted.append(proposal)
            seen_keys.add(key)
            if len(accepted) >= self._max_accepted:
                inhibited.extend(adjusted_proposal for adjusted_proposal in adjusted if (
                    adjusted_proposal not in accepted
                    and adjusted_proposal not in inhibited
                ))
                break
        return accepted, inhibited

    def _apply_repetition_inhibition(self, proposal: BroadcastProposal) -> BroadcastProposal:
        count = self._accepted_counts.get(_proposal_key(proposal), 0)
        if count == 0:
            return proposal
        priority = max(0.0, proposal.priority - (self._repetition_penalty * count))
        return replace(
            proposal,
            priority=priority,
            rationale=f"{proposal.rationale} Repeated proposal inhibited x{count}.",
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
        priority = 0.72
        if evidence.answer:
            priority += 0.18
        if evidence.supporting_evidence:
            priority += min(0.08, len(evidence.supporting_evidence) * 0.02)
        return (
            BroadcastProposal(
                subscriber=self.name,
                kind="resolve_answer",
                priority=min(priority, 0.98),
                rationale="Exact structured evidence matched the broadcast question.",
                payload={"evidence": collection_evidence_to_dict(evidence)},
            ),
        )


class SemanticRecallSubscriber:
    """Subscriber that proposes a follow-up memory query from broadcast entities."""

    name = "semantic_recall"

    def propose(self, context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
        broadcast_content = _broadcast_content(context.broadcast_text)
        entities = _broadcast_entities(broadcast_content)
        if not entities:
            return ()
        query = " ".join([entities[0], *_question_terms(context.question)[:3]])
        overlap = set(_question_terms(context.question)) & set(
            _question_terms(broadcast_content)
        )
        priority = 0.52 + min(0.18, len(overlap) * 0.04)
        return (
            BroadcastProposal(
                subscriber=self.name,
                kind="query_memory",
                priority=priority,
                rationale="Broadcast exposed an entity that may activate related memory.",
                payload={"query": query},
            ),
        )


class RelationContinuationSubscriber:
    """Subscriber that proposes continuing relation chains exposed by broadcast."""

    name = "relation_continuation"

    def propose(self, context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
        broadcast_content = _broadcast_content(context.broadcast_text)
        relation = _relation_term(context.question, broadcast_content)
        entities = _broadcast_entities(broadcast_content)
        if not relation or not entities:
            return ()
        priority = 0.68
        if relation.lower() in context.question.lower():
            priority += 0.08
        if len(entities) > 1:
            priority += 0.04
        return (
            BroadcastProposal(
                subscriber=self.name,
                kind="query_memory",
                priority=min(priority, 0.86),
                rationale="Broadcast contains a relation chain that may need continuation.",
                payload={"query": f"{entities[-1]} {relation}"},
            ),
        )


class ContradictionCheckerSubscriber:
    """Subscriber that flags obvious contradiction language in the broadcast."""

    name = "contradiction_checker"

    def __init__(self, markers: Sequence[str] = ()) -> None:
        self._markers = tuple(marker.lower().strip() for marker in markers if marker.strip())

    def propose(self, context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
        markers = _metadata_markers(context.metadata, self._markers)
        conflicts = _record_conflicts(context.context_chunks)
        lowered = context.broadcast_text.lower()
        matched_markers = [marker for marker in markers if marker in lowered]
        if not matched_markers and not conflicts:
            return ()
        priority = 0.74 + len(matched_markers) * 0.04 + len(conflicts) * 0.06
        return (
            BroadcastProposal(
                subscriber=self.name,
                kind="flag_contradiction",
                priority=min(priority, 0.94),
                rationale="Broadcast context contains contradiction evidence.",
                payload={"markers": matched_markers, "conflicts": conflicts},
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
        "inhibited": [_proposal_to_dict(proposal) for proposal in result.inhibited],
        "subscriber_reports": [
            {
                "subscriber": report.subscriber,
                "status": report.status,
                "proposal_count": report.proposal_count,
                "elapsed_ms": round(report.elapsed_ms, 3),
                "error": report.error,
            }
            for report in result.subscriber_reports
        ],
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


def _proposal_key(proposal: BroadcastProposal) -> tuple[str, str]:
    evidence = proposal.payload.get("evidence")
    answer = evidence.get("answer") if isinstance(evidence, Mapping) else None
    key = proposal.payload.get("query") or answer or proposal.payload.get("question")
    return (proposal.kind, str(key or proposal.subscriber).lower())


def _has_resolved_answer(proposals: Sequence[BroadcastProposal]) -> bool:
    for proposal in proposals:
        if proposal.kind != "resolve_answer":
            continue
        evidence = proposal.payload.get("evidence")
        if isinstance(evidence, Mapping) and evidence.get("answer"):
            return True
    return False


def _metadata_markers(
    metadata: Mapping[str, Any],
    defaults: Sequence[str],
) -> tuple[str, ...]:
    value = metadata.get("contradiction_markers", defaults)
    if isinstance(value, str):
        raw_markers: Sequence[object] = (value,)
    elif isinstance(value, Sequence):
        raw_markers = value
    else:
        raw_markers = defaults
    return tuple(str(marker).lower().strip() for marker in raw_markers if str(marker).strip())


def _record_conflicts(chunks: Sequence[str]) -> list[dict[str, Any]]:
    values_by_record: dict[tuple[str, str], dict[str, set[str] | str]] = {}
    for chunk in chunks:
        record = parse_record(chunk)
        if record is None:
            continue
        for field_name, value in record.fields.items():
            if field_name in {"id", "name"}:
                continue
            key = (record.record_id, field_name)
            entry = values_by_record.setdefault(
                key,
                {"values": set(), "record_id": record.record_id, "field": field_name},
            )
            values = entry["values"]
            if isinstance(values, set):
                values.add(str(value).lower())
    conflicts: list[dict[str, Any]] = []
    for entry in values_by_record.values():
        values = entry["values"]
        if not isinstance(values, set) or len(values) < 2:
            continue
        conflicts.append(
            {
                "record_id": entry["record_id"],
                "field": entry["field"],
                "values": sorted(values),
            }
        )
    return conflicts


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _question_terms(question: str) -> list[str]:
    return [
        token.strip(" ?'\".,").lower()
        for token in question.split()
        if len(token.strip(" ?'\".,")) > 3
    ][:6]


def _broadcast_entities(text: str) -> list[str]:
    pattern = re.compile(r"\b[A-Z][A-Za-z0-9.-]*(?:\s+[A-Z][A-Za-z0-9.-]*){0,4}")
    return _dedupe(match.group(0).strip() for match in pattern.finditer(text))


def _broadcast_content(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("[GOALS:")
            or stripped.startswith("[ADMITTED:")
            or stripped.startswith("[EVICTED:")
            or stripped.startswith("===")
        ):
            continue
        lines.append(re.sub(r"^\[slot:[^\]]+\]\s*", "", stripped))
    return "\n".join(lines)


def _relation_term(question: str, broadcast_text: str) -> str:
    for relation in _arrow_relations(broadcast_text):
        return relation
    possessive = re.findall(
        r"'s\s+([a-z][a-z0-9_ -]{2,48}?)(?:'s|\?| was | is |$)",
        question,
    )
    if possessive:
        return " ".join(possessive[-1].split())
    relation_question = re.search(
        r"\b(?:relationship|relation|edge|link)\s+['\"]?([a-z][a-z0-9_ -]{2,48})",
        question.lower(),
    )
    if relation_question:
        return " ".join(relation_question.group(1).split())
    return ""


def _arrow_relations(text: str) -> list[str]:
    relations: list[str] = []
    relations.extend(
        match.strip()
        for match in re.findall(r"-+([A-Za-z][A-Za-z0-9_ -]{1,48}?)-+>", text)
    )
    relations.extend(
        match.strip()
        for match in re.findall(r"->\s*([A-Za-z][A-Za-z0-9_ -]{1,48}?)\s*->", text)
    )
    return _dedupe(relations)


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
