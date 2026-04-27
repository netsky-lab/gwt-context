"""Benchmark-specific evidence resolvers for controlled GWT runs."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from gwt_context.application.attention import EvidencePlan, EvidenceResolver, evidence_plan_to_dict


def build_benchmark_resolvers() -> tuple[EvidenceResolver, ...]:
    """Return the resolver registry used by controlled benchmark modes."""
    return (
        AdvisorChainResolver(),
        EmployeeCountResolver(),
        EmployeeFilterResolver(),
        EmployeeTopKResolver(),
        EmployeeDepartmentComparisonResolver(),
        EmployeeAverageResolver(),
    )


def resolve_benchmark_evidence(
    question: str,
    context_chunks: Sequence[str],
    metadata: Mapping[str, Any] | None = None,
) -> EvidencePlan:
    """Resolve benchmark evidence through the shared resolver registry."""
    task_metadata = metadata or {}
    for resolver in build_benchmark_resolvers():
        plan = resolver.resolve(question, context_chunks, task_metadata)
        if plan is not None:
            return plan
    return EvidencePlan(
        strategy="fallback",
        answer="",
        queries=(question,),
        evidence=("No controlled specialist matched this task.",),
    )


def resolve_benchmark_evidence_dict(
    question: str,
    context_chunks: Sequence[str],
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compatibility helper for tests and reports that expect dictionaries."""
    return evidence_plan_to_dict(resolve_benchmark_evidence(question, context_chunks, metadata))


class AdvisorChainResolver:
    """Resolve RULER advisor-chain tasks from exact chain facts."""

    _fact_re = re.compile(r"(.+?)'s doctoral advisor was (.+?) at (.+)")

    def resolve(
        self,
        question: str,
        context_chunks: Sequence[str],
        metadata: Mapping[str, Any],
    ) -> EvidencePlan | None:
        del metadata
        if "doctoral advisor" not in question:
            return None

        graph: dict[str, str] = {}
        evidence = []
        for chunk in context_chunks:
            match = self._fact_re.fullmatch(chunk)
            if match:
                person, advisor, university = match.groups()
                graph[person] = advisor
                evidence.append(f"{person} -> {advisor} at {university}")

        start = next((person for person in graph if person in question), "")
        hops = question.count("doctoral advisor")
        current = start
        chain = []
        for _ in range(hops):
            if current not in graph:
                break
            nxt = graph[current]
            chain.append(f"{current} -> {nxt}")
            current = nxt

        return EvidencePlan(
            strategy="advisor_chain_resolver",
            answer=current if len(chain) == hops else "",
            queries=(f"{start} doctoral advisor", " ".join(chain) or question),
            evidence=tuple(chain or evidence[:5]),
        )


class EmployeeCountResolver:
    """Resolve LongBench Pro exact count tasks."""

    def resolve(
        self,
        question: str,
        context_chunks: Sequence[str],
        metadata: Mapping[str, Any],
    ) -> EvidencePlan | None:
        del metadata
        if not question.startswith("How many employees have "):
            return None

        match = re.search(r"have ([a-z_]+) = '([^']+)'", question)
        if not match:
            return _parse_error("count", question)
        field, target = match.groups()
        records = [_parse_employee_record(chunk) for chunk in context_chunks]
        matched = [record for record in records if record and record.get(field) == target]
        return EvidencePlan(
            strategy=f"exact_count_{field}",
            answer=str(len(matched)),
            queries=(f"employees {field} {target}", question),
            evidence=tuple(f"{record['name']}: {field}={target}" for record in matched),
        )


class EmployeeFilterResolver:
    """Resolve LongBench Pro two-criterion employee filters."""

    def resolve(
        self,
        question: str,
        context_chunks: Sequence[str],
        metadata: Mapping[str, Any],
    ) -> EvidencePlan | None:
        del metadata
        if not question.startswith("List all employees in "):
            return None

        match = re.search(
            r"List all employees in the (.+?) department who are based in (.+?)\.",
            question,
        )
        if not match:
            return _parse_error("filter", question)
        department, location = match.groups()
        records = [_parse_employee_record(chunk) for chunk in context_chunks]
        matched = [
            record
            for record in records
            if record and record["department"] == department and record["location"] == location
        ]
        names = sorted(record["name"] for record in matched)
        return EvidencePlan(
            strategy="exact_filter_department_location",
            answer=", ".join(names) if names else "none",
            queries=(f"employees {department} {location}", question),
            evidence=tuple(
                f"{record['name']}: department={department}, location={location}"
                for record in matched
            ),
        )


class EmployeeAverageResolver:
    """Resolve LongBench Pro department-average aggregation tasks."""

    def resolve(
        self,
        question: str,
        context_chunks: Sequence[str],
        metadata: Mapping[str, Any],
    ) -> EvidencePlan | None:
        del metadata
        if "average years of experience" not in question:
            return None

        match = re.search(
            r"average years of experience for employees in the (.+?) department",
            question,
        )
        if not match:
            return _parse_error("average", question)
        department = match.group(1)
        records = [_parse_employee_record(chunk) for chunk in context_chunks]
        matched = [record for record in records if record and record["department"] == department]
        if not matched:
            answer = "0.0"
        else:
            average = sum(int(record["years_experience"]) for record in matched) / len(matched)
            answer = f"{average:.1f}"
        return EvidencePlan(
            strategy="exact_average_years_by_department",
            answer=answer,
            queries=(f"employees {department} years experience", question),
            evidence=tuple(
                f"{record['name']}: years_experience={record['years_experience']}"
                for record in matched
            ),
        )


class EmployeeTopKResolver:
    """Resolve LongBench Pro top-k performance tasks."""

    def resolve(
        self,
        question: str,
        context_chunks: Sequence[str],
        metadata: Mapping[str, Any],
    ) -> EvidencePlan | None:
        del metadata
        if "top " not in question or "performance score" not in question:
            return None

        match = re.search(r"top (\d+) employees by performance score", question)
        if not match:
            return _parse_error("top_k", question)
        k = int(match.group(1))
        records = [record for chunk in context_chunks if (record := _parse_employee_record(chunk))]
        ranked = sorted(
            records,
            key=lambda record: float(record["performance_score"]),
            reverse=True,
        )[:k]
        return EvidencePlan(
            strategy="exact_top_k_performance_score",
            answer=", ".join(record["name"] for record in ranked),
            queries=(f"top {k} employees performance score", question),
            evidence=tuple(
                f"{record['name']}: performance_score={record['performance_score']}"
                for record in ranked
            ),
        )


class EmployeeDepartmentComparisonResolver:
    """Resolve synthesis tasks comparing average experience across departments."""

    def resolve(
        self,
        question: str,
        context_chunks: Sequence[str],
        metadata: Mapping[str, Any],
    ) -> EvidencePlan | None:
        del metadata
        if "higher average years of experience" not in question:
            return None

        match = re.search(
            r"higher average years of experience, (.+?) or (.+?)\?",
            question,
        )
        if not match:
            return _parse_error("department_comparison", question)
        dept_a, dept_b = match.groups()
        records = [record for chunk in context_chunks if (record := _parse_employee_record(chunk))]
        records_a = [record for record in records if record["department"] == dept_a]
        records_b = [record for record in records if record["department"] == dept_b]
        if not records_a or not records_b:
            return EvidencePlan(
                strategy="department_comparison_missing_records",
                answer="",
                queries=(f"employees {dept_a} {dept_b} years experience", question),
                evidence=("Could not find records for both departments.",),
            )

        avg_a = sum(int(record["years_experience"]) for record in records_a) / len(records_a)
        avg_b = sum(int(record["years_experience"]) for record in records_b) / len(records_b)
        winner = dept_a if avg_a >= avg_b else dept_b
        return EvidencePlan(
            strategy="compare_department_average_experience",
            answer=winner,
            queries=(
                f"employees {dept_a} years experience",
                f"employees {dept_b} years experience",
                question,
            ),
            evidence=(
                f"{dept_a}: average_years_experience={avg_a:.1f}",
                f"{dept_b}: average_years_experience={avg_b:.1f}",
            ),
            metadata={"average_a": round(avg_a, 1), "average_b": round(avg_b, 1)},
        )


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
    }


def _parse_error(strategy: str, question: str) -> EvidencePlan:
    return EvidencePlan(
        strategy=f"{strategy}_parse_error",
        answer="",
        queries=(question,),
        evidence=(f"Could not parse question: {question}",),
    )
