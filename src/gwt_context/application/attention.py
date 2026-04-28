"""Goal-directed attention control for workspace admission.

The controller coordinates the reusable GWT loop:
set the task goal, resolve a compact evidence plan, admit query matches into
competition, then run one or more selection-broadcast cycles.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from gwt_context.application.broadcast_bus import (
    BroadcastBus,
    BroadcastBusResult,
    BroadcastContext,
    BroadcastProposal,
    broadcast_bus_result_to_dict,
)
from gwt_context.application.structured import (
    CollectionEvidence,
    collection_evidence_to_dict,
    resolve_collection_evidence,
    resolve_relation_evidence,
)
from gwt_context.domain.models import MemoryType
from gwt_context.interfaces.ports import CyclePort, IngestionPort


@dataclass(frozen=True)
class EvidencePlan:
    """Resolved evidence and routing queries for one attention task."""

    strategy: str
    answer: str = ""
    queries: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


class EvidenceResolver(Protocol):
    """Contract for task-specific evidence planners."""

    def resolve(
        self,
        question: str,
        context_chunks: Sequence[str],
        metadata: Mapping[str, Any],
    ) -> EvidencePlan | None:
        """Return an evidence plan if this resolver can handle the task."""
        ...


@dataclass(frozen=True)
class AttentionStep:
    """One controller action useful for traces and audits."""

    phase: str
    name: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class BusAdmissionPolicy:
    """Policy for applying accepted broadcast-bus proposals."""

    min_resolve_priority: float = 0.7
    min_query_priority: float = 0.55
    suppress_queries_after_resolution: bool = True

    def decision(
        self,
        proposal: BroadcastProposal,
        *,
        resolved_answer: bool,
        deterministic_answer: bool,
    ) -> tuple[bool, str]:
        """Return whether a proposal should produce a controller side effect."""
        if proposal.kind == "resolve_answer":
            accepted = proposal.priority >= self.min_resolve_priority
            return accepted, "resolve_priority" if accepted else "resolve_below_threshold"
        if proposal.kind == "query_memory":
            if (
                self.suppress_queries_after_resolution
                and (resolved_answer or deterministic_answer)
            ):
                return False, "suppressed_after_resolution"
            accepted = proposal.priority >= self.min_query_priority
            return accepted, "query_priority" if accepted else "query_below_threshold"
        return True, "metadata_only"


@dataclass(frozen=True)
class AttentionRun:
    """Result of a controller run."""

    evidence: EvidencePlan
    tool_call_count: int
    broadcast_text: str
    admitted_ids: tuple[str, ...]
    steps: tuple[AttentionStep, ...]
    pass_count: int = 1


class AttentionTraceStore:
    """In-memory read model for the most recent attention run."""

    def __init__(self) -> None:
        self._last: dict[str, Any] | None = None

    def record(self, question: str, run: AttentionRun) -> dict[str, Any]:
        """Record and return a serializable trace for an attention run."""
        trace = attention_run_to_dict(question, run)
        self._last = trace
        return trace

    def get_last(self) -> dict[str, Any] | None:
        """Return the most recently recorded attention trace, if any."""
        return self._last


class AttentionController:
    """Reusable controller for explicit GWT selection/admission.

    The controller does not know benchmark task schemas. It accepts resolver
    objects that produce an ``EvidencePlan`` and executes the same bounded GWT
    loop against application ports.
    """

    def __init__(
        self,
        cycle: CyclePort,
        ingestion: IngestionPort,
        resolvers: Sequence[EvidenceResolver] = (),
        *,
        query_k: int = 10,
        admit_query_results: bool = True,
        broadcast_bus: BroadcastBus | None = None,
        bus_admission_policy: BusAdmissionPolicy | None = None,
    ) -> None:
        self._cycle = cycle
        self._ingestion = ingestion
        self._resolvers = tuple(resolvers)
        self._query_k = query_k
        self._admit_query_results = admit_query_results
        self._broadcast_bus = broadcast_bus
        self._bus_admission_policy = bus_admission_policy or BusAdmissionPolicy()

    def run(
        self,
        question: str,
        context_chunks: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
        keywords: Sequence[str] | None = None,
        passes: int = 1,
    ) -> AttentionRun:
        """Execute goal setting, evidence routing, query admission, and broadcast."""
        if passes < 1:
            raise ValueError("passes must be >= 1")

        task_metadata = metadata or {}
        steps: list[AttentionStep] = []
        goal_keywords = tuple(keywords or extract_question_keywords(question))
        goal = self._cycle.set_goal(description=question, keywords=list(goal_keywords))
        steps.append(
            AttentionStep(
                phase="controller_tool",
                name="gwt_set_goal",
                payload={
                    "goal_id": goal.id,
                    "description": goal.description,
                    "keywords": list(goal_keywords),
                },
            )
        )

        plan = self._resolve(question, context_chunks, task_metadata)
        steps.append(
            AttentionStep(
                phase="controller",
                name="evidence_plan",
                payload=evidence_plan_to_dict(plan),
            )
        )

        admitted_ids: list[str] = []
        tool_call_count = 1
        broadcast_text = ""
        completed_passes = 0
        seen_queries: set[str] = set()
        pre_admitted = False

        workspace_summary = _metadata_text(plan.metadata, "workspace_summary")
        if workspace_summary:
            item = self._ingestion.ingest(
                content=workspace_summary,
                memory_type=MemoryType.WORKING,
                source="attention:collection_summary",
                tags=["attention", "collection"],
            )
            item.activation_level = 1.0
            item.access_count = max(item.access_count, 20)
            self._cycle.enqueue_for_competition(item)
            admitted_ids.append(item.id)
            pre_admitted = True
            tool_call_count += 1
            steps.append(
                AttentionStep(
                    phase="controller_tool",
                    name="gwt_store",
                    payload={
                        "item_id": item.id,
                        "source": "attention:collection_summary",
                        "content_preview": workspace_summary[:240],
                    },
                )
            )

        for pass_number in range(1, passes + 1):
            queries = _queries_for_pass(question, plan, broadcast_text, seen_queries, pass_number)
            if not queries and not (pass_number == 1 and pre_admitted):
                break

            for query in queries:
                seen_queries.add(query.lower())
                items = self._ingestion.query_similar(query=query, k=self._query_k)
                tool_call_count += 1
                query_ids = []
                for item in items:
                    query_ids.append(item.id)
                    if self._admit_query_results:
                        self._cycle.enqueue_for_competition(item)
                        admitted_ids.append(item.id)
                steps.append(
                    AttentionStep(
                        phase="controller_tool",
                        name="gwt_query",
                        payload={
                            "pass": pass_number,
                            "query": query,
                            "k": self._query_k,
                            "matched_ids": query_ids,
                            "admitted_ids": list(query_ids)
                            if self._admit_query_results
                            else [],
                        },
                    )
                )

            record = self._cycle.run(
                question=question,
                evidence_plan=plan,
                context_chunks=tuple(context_chunks),
                metadata=task_metadata,
                pass_number=pass_number,
            )
            tool_call_count += 1
            completed_passes += 1
            broadcast_text = record.formatted_content
            steps.append(
                AttentionStep(
                    phase="controller_tool",
                    name="gwt_broadcast",
                    payload={
                        "pass": pass_number,
                        "broadcast_id": record.id,
                        "record_admitted_ids": record.admitted_ids,
                        "record_evicted_ids": record.evicted_ids,
                    },
                )
            )
            bus_result = self._last_bus_result_from_cycle()
            if bus_result is None and self._broadcast_bus is not None:
                bus_result = self._broadcast_bus.publish(
                    BroadcastContext(
                        question=question,
                        broadcast_id=str(record.id),
                        broadcast_text=broadcast_text,
                        pass_number=pass_number,
                        evidence_plan=plan,
                        context_chunks=tuple(context_chunks),
                        metadata=task_metadata,
                    )
                )
            if bus_result is not None:
                steps.append(
                    AttentionStep(
                        phase="broadcast_bus",
                        name="broadcast_subscribers",
                        payload=broadcast_bus_result_to_dict(bus_result),
                    )
                )
                resolved_by_bus = False
                for proposal in bus_result.accepted:
                    should_apply, reason = self._bus_admission_policy.decision(
                        proposal,
                        resolved_answer=resolved_by_bus,
                        deterministic_answer=bool(plan.metadata.get("deterministic_answer")),
                    )
                    if not should_apply:
                        steps.append(
                            _proposal_step(
                                pass_number,
                                proposal,
                                "subscriber_policy_skip",
                                {"reason": reason},
                            )
                        )
                        continue
                    if proposal.kind == "query_memory":
                        query_count, query_admitted = self._apply_query_proposal(
                            proposal,
                            seen_queries,
                            admitted_ids,
                            pass_number,
                            steps,
                        )
                        tool_call_count += query_count
                        if query_admitted:
                            continue
                    elif proposal.kind == "resolve_answer":
                        plan = _plan_with_resolved_answer(plan, proposal)
                        resolved_by_bus = True
                        steps.append(
                            _proposal_step(
                                pass_number,
                                proposal,
                                "subscriber_resolve",
                                {"policy_reason": reason},
                            )
                        )
                    elif proposal.kind == "flag_contradiction":
                        plan = _plan_with_metadata_flag(plan, "contradiction", proposal.payload)
                        steps.append(
                            _proposal_step(
                                pass_number,
                                proposal,
                                "subscriber_flag",
                                {"policy_reason": reason},
                            )
                        )
                    elif proposal.kind == "ask_followup":
                        plan = _plan_with_metadata_flag(plan, "followup", proposal.payload)
                        steps.append(
                            _proposal_step(
                                pass_number,
                                proposal,
                                "subscriber_followup",
                                {"policy_reason": reason},
                            )
                        )

        return AttentionRun(
            evidence=plan,
            tool_call_count=tool_call_count,
            broadcast_text=broadcast_text,
            admitted_ids=tuple(admitted_ids),
            steps=tuple(steps),
            pass_count=completed_passes,
        )

    def _last_bus_result_from_cycle(self) -> Any | None:
        getter = getattr(self._cycle, "get_last_broadcast_bus_result", None)
        if getter is None:
            return None
        result = getter()
        return result if isinstance(result, BroadcastBusResult) else None

    def _apply_query_proposal(
        self,
        proposal: BroadcastProposal,
        seen_queries: set[str],
        admitted_ids: list[str],
        pass_number: int,
        steps: list[AttentionStep],
    ) -> tuple[int, bool]:
        query = _metadata_text(proposal.payload, "query")
        if not query or query.lower() in seen_queries:
            return 0, False
        seen_queries.add(query.lower())
        items = self._ingestion.query_similar(query=query, k=self._query_k)
        query_ids = []
        for item in items:
            query_ids.append(item.id)
            if self._admit_query_results:
                self._cycle.enqueue_for_competition(item)
                admitted_ids.append(item.id)
        steps.append(
            AttentionStep(
                phase="broadcast_bus_tool",
                name="subscriber_query",
                payload={
                    "pass": pass_number,
                    "subscriber": proposal.subscriber,
                    "query": query,
                    "matched_ids": query_ids,
                    "admitted_ids": list(query_ids)
                    if self._admit_query_results
                    else [],
                },
            )
        )
        return 1, True

    def _resolve(
        self,
        question: str,
        context_chunks: Sequence[str],
        metadata: Mapping[str, Any],
    ) -> EvidencePlan:
        for resolver in self._resolvers:
            plan = resolver.resolve(question, context_chunks, metadata)
            if plan is not None:
                return plan
        return EvidencePlan(
            strategy="fallback",
            answer="",
            queries=(question,),
            evidence=("No evidence resolver matched this task.",),
        )


class GenericEvidenceResolver:
    """Production-safe resolver that plans semantic queries from the question.

    It does not infer task-specific answers. Its job is to select a compact set
    of semantic lookup queries that can admit relevant memories into the
    workspace before model reasoning.
    """

    def __init__(self, max_queries: int = 6, planner: str = "auto") -> None:
        self._max_queries = max_queries
        self._planner = _normalize_planner(planner)

    def resolve(
        self,
        question: str,
        context_chunks: Sequence[str],
        metadata: Mapping[str, Any],
    ) -> EvidencePlan:
        if self._planner in {"auto", "generic", "hybrid", "structured"}:
            collection_plan = _resolve_collection_plan(question, context_chunks, metadata)
            if collection_plan is not None:
                return collection_plan
            if self._planner == "structured":
                return EvidencePlan(
                    strategy="structured_no_collection_match",
                    queries=(),
                    evidence=("No structured collection evidence matched this task.",),
                    metadata={"planner": "structured"},
                )

        if self._planner in {"auto", "generic", "hybrid", "graph"}:
            relation_plan = _resolve_relation_plan(question, context_chunks, metadata)
            if relation_plan is not None:
                return relation_plan
            if self._planner == "graph":
                return EvidencePlan(
                    strategy="graph_no_relation_match",
                    queries=(),
                    evidence=("No relation graph evidence matched this task.",),
                    metadata={"planner": "graph"},
                )

        queries = _dedupe_preserving_order(
            [
                question,
                *_metadata_queries(metadata),
                *_structured_queries(question),
                *_relation_queries(question),
                *_quoted_phrases(question),
                *_capitalized_phrases(question),
                " ".join(extract_question_keywords(question, limit=6)),
            ]
        )
        bounded = tuple(query for query in queries if query)[: self._max_queries]
        return EvidencePlan(
            strategy="generic_semantic_query_planner",
            queries=bounded or (question,),
            evidence=("Generic planner selected semantic queries from the question.",),
            metadata={"planner": "semantic", "query_count": len(bounded or (question,))},
        )


def supported_planners() -> tuple[str, ...]:
    """Return supported production planner modes."""
    return ("auto", "generic", "semantic", "structured", "graph", "hybrid")


def _normalize_planner(planner: str) -> str:
    normalized = planner.lower().strip()
    return normalized if normalized in supported_planners() else "auto"


def _resolve_collection_plan(
    question: str,
    context_chunks: Sequence[str],
    metadata: Mapping[str, Any],
) -> EvidencePlan | None:
    evidence = resolve_collection_evidence(question, context_chunks, metadata)
    if evidence is None:
        return None
    return _collection_evidence_to_plan(question, evidence)


def _resolve_relation_plan(
    question: str,
    context_chunks: Sequence[str],
    metadata: Mapping[str, Any],
) -> EvidencePlan | None:
    evidence = resolve_relation_evidence(question, context_chunks, metadata)
    if evidence is None:
        return None
    return _collection_evidence_to_plan(question, evidence)


def _collection_evidence_to_plan(question: str, evidence: CollectionEvidence) -> EvidencePlan:
    metadata = {
        **dict(evidence.metadata),
        "collection_evidence": collection_evidence_to_dict(evidence),
        "workspace_summary": evidence.render(question),
    }
    return EvidencePlan(
        strategy=evidence.strategy,
        answer=evidence.answer,
        queries=(),
        evidence=evidence.supporting_evidence,
        metadata=metadata,
    )


def evidence_plan_to_dict(plan: EvidencePlan) -> dict[str, Any]:
    """Convert an evidence plan to a JSON-serializable payload."""
    return {
        "strategy": plan.strategy,
        "answer": plan.answer,
        "queries": list(plan.queries),
        "evidence": list(plan.evidence),
        "metadata": dict(plan.metadata),
    }


def attention_run_to_dict(question: str, run: AttentionRun) -> dict[str, Any]:
    """Convert an attention run to a JSON-serializable trace."""
    return {
        "question": question,
        "evidence_plan": evidence_plan_to_dict(run.evidence),
        "tool_call_count": run.tool_call_count,
        "pass_count": run.pass_count,
        "admitted_ids": list(run.admitted_ids),
        "broadcast": run.broadcast_text,
        "trace": [
            {
                "phase": step.phase,
                "name": step.name,
                "payload": dict(step.payload),
            }
            for step in run.steps
        ],
    }


def _plan_with_resolved_answer(plan: EvidencePlan, proposal: BroadcastProposal) -> EvidencePlan:
    evidence = proposal.payload.get("evidence")
    if not isinstance(evidence, Mapping):
        return plan
    answer = evidence.get("answer")
    if not isinstance(answer, str) or not answer:
        return plan
    supporting = evidence.get("supporting_evidence", ())
    supporting_evidence = (
        tuple(str(item) for item in supporting)
        if isinstance(supporting, Sequence) and not isinstance(supporting, str)
        else ()
    )
    metadata = {
        **dict(plan.metadata),
        "deterministic_answer": True,
        "broadcast_bus_resolution": {
            "subscriber": proposal.subscriber,
            "priority": proposal.priority,
            "evidence": dict(evidence),
        },
    }
    return replace(
        plan,
        answer=answer,
        evidence=supporting_evidence or plan.evidence,
        metadata=metadata,
    )


def _plan_with_metadata_flag(
    plan: EvidencePlan,
    key: str,
    payload: Mapping[str, Any],
) -> EvidencePlan:
    flags = dict(plan.metadata.get("broadcast_bus_flags", {}))
    flags[key] = dict(payload)
    return replace(plan, metadata={**dict(plan.metadata), "broadcast_bus_flags": flags})


def _proposal_step(
    pass_number: int,
    proposal: BroadcastProposal,
    name: str,
    extra_payload: Mapping[str, Any] | None = None,
) -> AttentionStep:
    payload = {
        "pass": pass_number,
        "subscriber": proposal.subscriber,
        "kind": proposal.kind,
        "priority": proposal.priority,
        "payload": dict(proposal.payload),
    }
    if extra_payload:
        payload.update(extra_payload)
    return AttentionStep(
        phase="broadcast_bus_tool",
        name=name,
        payload=payload,
    )


def extract_question_keywords(question: str, limit: int = 8) -> list[str]:
    """Extract stable lightweight keywords from a natural-language question."""
    return [
        token.strip(" ?'\".,").lower()
        for token in question.split()
        if len(token.strip(" ?'\".,")) > 3
    ][:limit]


def _relation_queries(text: str) -> list[str]:
    lowered = text.lower()
    phrases: list[str] = []
    for relation in (
        "doctoral advisor",
        "worked with",
        "average years of experience",
        "performance score",
        "based in",
        "department",
        "project",
        "status",
    ):
        if relation in lowered:
            entities = _quoted_phrases(text) + _capitalized_phrases(text)
            if entities:
                phrases.extend(f"{entity} {relation}" for entity in entities[:4])
            phrases.append(relation)
    return phrases


def _queries_for_pass(
    question: str,
    plan: EvidencePlan,
    broadcast_text: str,
    seen_queries: set[str],
    pass_number: int,
) -> tuple[str, ...]:
    if bool(plan.metadata.get("skip_semantic_queries")):
        return ()
    if pass_number == 1:
        raw_queries = plan.queries or (question,)
    else:
        raw_queries = tuple(_follow_up_queries(question, broadcast_text, plan))
    queries = _dedupe_preserving_order(raw_queries)
    return tuple(query for query in queries if query.lower() not in seen_queries)


def _follow_up_queries(question: str, broadcast_text: str, plan: EvidencePlan) -> list[str]:
    """Build second-pass queries from the current broadcast without domain state access."""
    relation_terms = _relation_terms(question)
    entities = _broadcast_entities(broadcast_text)
    queries: list[str] = []
    for entity in entities[:4]:
        for relation in relation_terms[:2]:
            queries.append(f"{entity} {relation}")
    for query in plan.queries[:2]:
        queries.append(" ".join([query, "related evidence"]))
    return _dedupe_preserving_order(queries)[:4]


def _relation_terms(text: str) -> list[str]:
    lowered = text.lower()
    terms: list[str] = []
    for relation in (
        "doctoral advisor",
        "worked with",
        "average years of experience",
        "performance score",
        "based in",
        "department",
        "project",
        "status",
    ):
        if relation in lowered:
            terms.append(relation)
    return terms or ["related evidence"]


def _broadcast_entities(text: str) -> list[str]:
    entities: list[str] = []
    patterns = (
        r"\bwas\s+([A-Z][A-Za-z0-9.-]*(?:\s+[A-Z][A-Za-z0-9.-]*){0,3})\s+at\b",
        r"\bwith\s+([A-Z][A-Za-z0-9.-]*(?:\s+[A-Z][A-Za-z0-9.-]*){0,3})\b",
        r"\bin\s+the\s+([A-Z][A-Za-z0-9.-]*(?:\s+[A-Z][A-Za-z0-9.-]*){0,3})\s+department\b",
    )
    for pattern in patterns:
        entities.extend(match.strip() for match in re.findall(pattern, text))
    entities.extend(_capitalized_phrases(text))
    return _dedupe_preserving_order(entities)


def _metadata_queries(metadata: Mapping[str, Any]) -> list[str]:
    queries: list[str] = []
    field = str(metadata.get("field", "")).strip()
    target = str(metadata.get("target", "")).strip()
    if field and target:
        queries.extend(_field_target_queries(field, target))

    department = str(metadata.get("department", "")).strip()
    if department:
        queries.extend(_department_queries(department))

    department_a = str(metadata.get("department_a", "")).strip()
    department_b = str(metadata.get("department_b", "")).strip()
    for department_name in (department_a, department_b):
        if department_name:
            queries.extend(_department_queries(department_name))

    if metadata.get("task_type") == "top_k" or "k" in metadata:
        queries.extend(
            [
                "top employees performance score",
                "highest performance score employees",
                "performance score",
            ]
        )
    return queries


def _structured_queries(question: str) -> list[str]:
    queries: list[str] = []
    for field_name, target in re.findall(
        r"\b(?:have|with)\s+([a-z_]+)\s*=\s*'([^']+)'",
        question,
    ):
        queries.extend(_field_target_queries(field_name, target))

    dept_match = re.search(
        r"employees in the ([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*) department",
        question,
    )
    if dept_match:
        queries.extend(_department_queries(dept_match.group(1)))

    filter_match = re.search(
        r"employees in the ([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*) department "
        r"who are based in ([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*)",
        question,
    )
    if filter_match:
        department, location = filter_match.groups()
        queries.extend(
            [
                f"employees {department} department based in {location}",
                f"{department} {location} employees",
                f"based in {location}",
            ]
        )

    comparison_match = re.search(
        r"experience,\s+(.+?)\s+or\s+(.+?)\?",
        question,
    )
    if comparison_match:
        for department in comparison_match.groups():
            queries.extend(_department_queries(department.strip()))

    if "performance score" in question.lower():
        queries.extend(
            [
                "top employees performance score",
                "highest performance score employees",
                "performance score",
            ]
        )
    return queries


def _field_target_queries(field: str, target: str) -> list[str]:
    normalized_field = field.strip().replace("_", " ")
    normalized_target = target.strip()
    queries = [
        f"employees {normalized_field} {normalized_target}",
        f"{normalized_target} {normalized_field}",
    ]
    if normalized_field == "department":
        queries.extend(_department_queries(normalized_target))
    if normalized_field == "status":
        queries.append(f"Status: {normalized_target}")
    if normalized_field == "location":
        queries.append(f"based in {normalized_target}")
    if normalized_field == "project":
        queries.append(f"assigned to {normalized_target}")
    queries.append(f"{normalized_field}: {normalized_target}")
    return queries


def _department_queries(department: str) -> list[str]:
    department_name = department.strip()
    return [
        f"{department_name} department",
        f"employees in {department_name} department",
        f"{department_name} department years experience",
        f"{department_name} average years of experience",
    ]


def _metadata_text(metadata: Mapping[str, Any], key: str) -> str:
    value = metadata.get(key)
    return value if isinstance(value, str) else ""


def _quoted_phrases(text: str) -> list[str]:
    phrases: list[str] = []
    for match in re.findall(r"'([^']+)'|\"([^\"]+)\"", text):
        phrases.extend(value.strip() for value in match if value.strip())
    return phrases


def _capitalized_phrases(text: str) -> list[str]:
    pattern = re.compile(r"\b[A-Z][A-Za-z0-9.-]*(?:\s+[A-Z][A-Za-z0-9.-]*){0,4}")
    return [match.group(0).strip() for match in pattern.finditer(text)]


def _dedupe_preserving_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        normalized = " ".join(value.split())
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        result.append(normalized)
        seen.add(key)
    return result
