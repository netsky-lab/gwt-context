"""Goal-directed attention control for workspace admission.

The controller coordinates the reusable GWT loop:
set the task goal, resolve a compact evidence plan, admit query matches into
competition, then run one selection-broadcast cycle.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

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
class AttentionRun:
    """Result of a controller run."""

    evidence: EvidencePlan
    tool_call_count: int
    broadcast_text: str
    admitted_ids: tuple[str, ...]
    steps: tuple[AttentionStep, ...]


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
    ) -> None:
        self._cycle = cycle
        self._ingestion = ingestion
        self._resolvers = tuple(resolvers)
        self._query_k = query_k
        self._admit_query_results = admit_query_results

    def run(
        self,
        question: str,
        context_chunks: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
        keywords: Sequence[str] | None = None,
    ) -> AttentionRun:
        """Execute goal setting, evidence routing, query admission, and broadcast."""
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
        queries = plan.queries or (question,)
        for query in queries:
            items = self._ingestion.query_similar(query=query, k=self._query_k)
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
                        "query": query,
                        "k": self._query_k,
                        "matched_ids": query_ids,
                        "admitted_ids": list(query_ids) if self._admit_query_results else [],
                    },
                )
            )

        record = self._cycle.run()
        steps.append(
            AttentionStep(
                phase="controller_tool",
                name="gwt_broadcast",
                payload={
                    "broadcast_id": record.id,
                    "record_admitted_ids": record.admitted_ids,
                    "record_evicted_ids": record.evicted_ids,
                },
            )
        )

        return AttentionRun(
            evidence=plan,
            tool_call_count=2 + len(queries),
            broadcast_text=record.formatted_content,
            admitted_ids=tuple(admitted_ids),
            steps=tuple(steps),
        )

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

    def __init__(self, max_queries: int = 4) -> None:
        self._max_queries = max_queries

    def resolve(
        self,
        question: str,
        context_chunks: Sequence[str],
        metadata: Mapping[str, Any],
    ) -> EvidencePlan:
        del context_chunks, metadata
        queries = _dedupe_preserving_order(
            [
                question,
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
            metadata={"planner": "generic", "query_count": len(bounded or (question,))},
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
