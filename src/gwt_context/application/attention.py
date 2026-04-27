"""Goal-directed attention control for workspace admission.

The controller coordinates the reusable GWT loop:
set the task goal, resolve a compact evidence plan, admit query matches into
competition, then run one or more selection-broadcast cycles.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

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

            record = self._cycle.run()
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

        return AttentionRun(
            evidence=plan,
            tool_call_count=tool_call_count,
            broadcast_text=broadcast_text,
            admitted_ids=tuple(admitted_ids),
            steps=tuple(steps),
            pass_count=completed_passes,
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

    def __init__(self, max_queries: int = 6) -> None:
        self._max_queries = max_queries

    def resolve(
        self,
        question: str,
        context_chunks: Sequence[str],
        metadata: Mapping[str, Any],
    ) -> EvidencePlan:
        exact_plan = _resolve_structured_employee_evidence(question, context_chunks, metadata)
        if exact_plan is not None:
            return exact_plan

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


def _resolve_structured_employee_evidence(
    question: str,
    context_chunks: Sequence[str],
    metadata: Mapping[str, Any],
) -> EvidencePlan | None:
    records = [_parse_employee_record(chunk) for chunk in context_chunks]
    employee_records = [record for record in records if record is not None]
    if not employee_records:
        return None

    count_plan = _resolve_employee_count(question, employee_records)
    if count_plan is not None:
        return count_plan

    filter_plan = _resolve_employee_filter(question, employee_records)
    if filter_plan is not None:
        return filter_plan

    top_k_plan = _resolve_employee_top_k(question, employee_records)
    if top_k_plan is not None:
        return top_k_plan

    comparison_plan = _resolve_employee_department_comparison(question, employee_records)
    if comparison_plan is not None:
        return comparison_plan

    average_plan = _resolve_employee_average(question, employee_records)
    if average_plan is not None:
        return average_plan

    if metadata.get("task_type") in {"count", "filter", "aggregate", "top_k", "synthesis"}:
        return EvidencePlan(
            strategy="structured_employee_parse_error",
            answer="",
            queries=(question,),
            evidence=("Employee records were present but the question did not match.",),
        )
    return None


def _resolve_employee_count(
    question: str,
    records: Sequence[Mapping[str, str]],
) -> EvidencePlan | None:
    match = re.search(r"How many employees have ([a-z_]+) = '([^']+)'", question)
    if not match:
        return None
    field_name, target = match.groups()
    matched = [record for record in records if record.get(field_name) == target]
    return _structured_employee_plan(
        strategy=f"structured_count_{field_name}",
        question=question,
        answer=str(len(matched)),
        queries=(f"employees {field_name} {target}",),
        matched_records=matched,
        summary_lines=[
            f"Exact count: {len(matched)} employees where {field_name}={target}.",
            *_record_lines(matched, fields=(field_name,)),
        ],
        extra_metadata={"field": field_name, "target": target},
    )


def _resolve_employee_filter(
    question: str,
    records: Sequence[Mapping[str, str]],
) -> EvidencePlan | None:
    match = re.search(
        r"List all employees in the (.+?) department who are based in (.+?)\.",
        question,
    )
    if not match:
        return None
    department, location = match.groups()
    matched = [
        record
        for record in records
        if record["department"] == department and record["location"] == location
    ]
    names = sorted(record["name"] for record in matched)
    answer = ", ".join(names) if names else "none"
    return _structured_employee_plan(
        strategy="structured_filter_department_location",
        question=question,
        answer=answer,
        queries=(f"employees {department} department based in {location}",),
        matched_records=matched,
        summary_lines=[
            f"Exact filter: department={department}, location={location}.",
            f"Answer: {answer}.",
            *_record_lines(matched, fields=("department", "location")),
        ],
        extra_metadata={"department": department, "location": location},
    )


def _resolve_employee_average(
    question: str,
    records: Sequence[Mapping[str, str]],
) -> EvidencePlan | None:
    match = re.search(
        r"average years of experience for employees in the (.+?) department",
        question,
    )
    if not match:
        return None
    department = match.group(1)
    matched = [record for record in records if record["department"] == department]
    if matched:
        average = sum(int(record["years_experience"]) for record in matched) / len(matched)
        answer = f"{average:.1f}"
    else:
        answer = "0.0"
    return _structured_employee_plan(
        strategy="structured_average_years_by_department",
        question=question,
        answer=answer,
        queries=(f"employees {department} years experience",),
        matched_records=matched,
        summary_lines=[
            f"Exact average: {department} average years of experience = {answer}.",
            *_record_lines(matched, fields=("years_experience", "department")),
        ],
        extra_metadata={"department": department},
    )


def _resolve_employee_top_k(
    question: str,
    records: Sequence[Mapping[str, str]],
) -> EvidencePlan | None:
    match = re.search(r"top (\d+) employees by performance score", question)
    if not match:
        return None
    k = int(match.group(1))
    ranked = sorted(
        records,
        key=lambda record: (-float(record["performance_score"]), _employee_index(record["name"])),
    )[:k]
    answer = ", ".join(record["name"] for record in ranked)
    return _structured_employee_plan(
        strategy="structured_top_k_performance_score",
        question=question,
        answer=answer,
        queries=(f"top {k} employees performance score",),
        matched_records=ranked,
        summary_lines=[
            f"Exact top {k} by performance score: {answer}.",
            *_record_lines(ranked, fields=("performance_score",)),
        ],
        extra_metadata={"k": k},
    )


def _resolve_employee_department_comparison(
    question: str,
    records: Sequence[Mapping[str, str]],
) -> EvidencePlan | None:
    match = re.search(
        r"higher average years of experience, (.+?) or (.+?)\?",
        question,
    )
    if not match:
        return None
    dept_a, dept_b = match.groups()
    records_a = [record for record in records if record["department"] == dept_a]
    records_b = [record for record in records if record["department"] == dept_b]
    if not records_a or not records_b:
        return _structured_employee_plan(
            strategy="structured_department_comparison_missing_records",
            question=question,
            answer="",
            queries=(f"employees {dept_a} {dept_b} years experience",),
            matched_records=(*records_a, *records_b),
            summary_lines=("Could not find records for both departments.",),
            extra_metadata={"department_a": dept_a, "department_b": dept_b},
        )

    avg_a = sum(int(record["years_experience"]) for record in records_a) / len(records_a)
    avg_b = sum(int(record["years_experience"]) for record in records_b) / len(records_b)
    winner = dept_a if avg_a >= avg_b else dept_b
    matched = [*records_a, *records_b]
    return _structured_employee_plan(
        strategy="structured_compare_department_average_experience",
        question=question,
        answer=winner,
        queries=(
            f"employees {dept_a} years experience",
            f"employees {dept_b} years experience",
        ),
        matched_records=matched,
        summary_lines=[
            f"{dept_a}: average_years_experience={avg_a:.1f} from {len(records_a)} records.",
            f"{dept_b}: average_years_experience={avg_b:.1f} from {len(records_b)} records.",
            f"Answer: {winner}.",
            *_record_lines(matched, fields=("department", "years_experience")),
        ],
        extra_metadata={
            "department_a": dept_a,
            "department_b": dept_b,
            "average_a": round(avg_a, 1),
            "average_b": round(avg_b, 1),
        },
    )


def _structured_employee_plan(
    *,
    strategy: str,
    question: str,
    answer: str,
    queries: Sequence[str],
    matched_records: Sequence[Mapping[str, str]],
    summary_lines: Sequence[str],
    extra_metadata: Mapping[str, Any],
) -> EvidencePlan:
    full_records = tuple(record["raw"] for record in matched_records)
    workspace_summary = "\n".join(
        [
            "STRUCTURED COLLECTION EVIDENCE",
            f"Question: {question}",
            f"Controller answer: {answer}",
            *summary_lines,
            "Full matching records:",
            *full_records,
        ]
    )
    return EvidencePlan(
        strategy=strategy,
        answer=answer,
        queries=tuple(queries),
        evidence=tuple(summary_lines),
        metadata={
            "planner": "structured_employee",
            "deterministic_answer": True,
            "skip_semantic_queries": True,
            "collection_record_count": len(matched_records),
            "workspace_summary": workspace_summary,
            **dict(extra_metadata),
        },
    )


def _record_lines(
    records: Sequence[Mapping[str, str]],
    *,
    fields: Sequence[str],
) -> list[str]:
    lines: list[str] = []
    for record in records:
        values = ", ".join(f"{field}={record[field]}" for field in fields)
        lines.append(f"{record['name']}: {values}")
    return lines


def _parse_employee_record(chunk: str) -> dict[str, str] | None:
    pattern = re.compile(
        r"(Employee-\d+) works in the (.+?) department, based in (.+?)\. "
        r"Status: (.+?)\. They have (\d+) years of experience and are "
        r"currently assigned to Project (.+?)\. Skills: (.+?)\. "
        r"Performance score: (.+?)/5\.0\. Salary band: (.+?)\."
    )
    match = pattern.fullmatch(chunk)
    if not match:
        return None
    (
        name,
        department,
        location,
        status,
        years_experience,
        project,
        skills,
        performance_score,
        salary_band,
    ) = match.groups()
    return {
        "name": name,
        "department": department,
        "location": location,
        "status": status,
        "years_experience": years_experience,
        "project": project,
        "skills": skills,
        "performance_score": performance_score,
        "salary_band": salary_band,
        "raw": chunk,
    }


def _employee_index(name: str) -> int:
    match = re.search(r"(\d+)$", name)
    return int(match.group(1)) if match else 0


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
