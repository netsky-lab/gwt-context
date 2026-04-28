"""Structured evidence primitives for exact collection and relation work."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

Scalar = str | float


@dataclass(frozen=True)
class StructuredRecord:
    """Parsed record-like memory item with normalized fields."""

    record_id: str
    fields: Mapping[str, Scalar]
    raw: str

    def text(self, field_name: str) -> str:
        """Return a normalized text value for a field."""
        value = self.fields.get(normalize_field_name(field_name), "")
        return _format_scalar(value)

    def number(self, field_name: str) -> float | None:
        """Return a numeric field value, if available."""
        value = self.fields.get(normalize_field_name(field_name))
        if isinstance(value, float):
            return value
        if isinstance(value, str):
            return _parse_number(value)
        return None


@dataclass(frozen=True)
class CollectionEvidence:
    """Computed evidence item for collection-style operations."""

    strategy: str
    operation: str
    answer: str
    matched_records: tuple[StructuredRecord, ...] = ()
    supporting_evidence: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def render(self, question: str) -> str:
        """Render compact collection evidence for workspace broadcast."""
        heading = (
            "RELATION GRAPH EVIDENCE"
            if self.operation == "relation_path"
            else "STRUCTURED COLLECTION EVIDENCE"
        )
        lines = [
            heading,
            f"Question: {question}",
            f"Operation: {self.operation}",
            f"Controller answer: {self.answer}",
            f"Matched records: {len(self.matched_records)}",
        ]
        lines.extend(self.supporting_evidence)
        if self.matched_records:
            lines.append("Full matching records:")
            lines.extend(record.raw for record in self.matched_records)
        return "\n".join(lines)


class CollectionIndex:
    """Runtime index over parsed record-like chunks."""

    def __init__(self, records: Sequence[StructuredRecord]) -> None:
        self._records = tuple(records)

    @classmethod
    def from_chunks(cls, chunks: Sequence[str]) -> CollectionIndex:
        """Build a collection index from raw memory chunks."""
        records: list[StructuredRecord] = []
        for chunk in chunks:
            records.extend(parse_records(chunk))
        return cls(records)

    @property
    def records(self) -> tuple[StructuredRecord, ...]:
        """Parsed records in insertion order."""
        return self._records

    @property
    def field_names(self) -> tuple[str, ...]:
        """All normalized field names found in this collection."""
        names: set[str] = set()
        for record in self._records:
            names.update(record.fields)
        return tuple(sorted(names))

    @property
    def numeric_field_names(self) -> tuple[str, ...]:
        """Field names that have at least one numeric value."""
        names: set[str] = set()
        for record in self._records:
            for field_name in record.fields:
                if record.number(field_name) is not None:
                    names.add(field_name)
        return tuple(sorted(names))

    def filter_equals(self, criteria: Mapping[str, str]) -> tuple[StructuredRecord, ...]:
        """Return records whose normalized fields equal all criteria."""
        normalized = {
            normalize_field_name(field_name): normalize_value(value)
            for field_name, value in criteria.items()
        }
        return tuple(record for record in self._records if _record_matches(record, normalized))

    def top_k(self, metric: str, k: int) -> tuple[StructuredRecord, ...]:
        """Return top-k records by a numeric metric with stable id tie-breaks."""
        metric_name = normalize_field_name(metric)
        ranked = [
            record for record in self._records if record.number(metric_name) is not None
        ]
        return tuple(
            sorted(
                ranked,
                key=lambda record: (
                    -(record.number(metric_name) or 0.0),
                    _record_sort_key(record.record_id),
                ),
            )[:k]
        )

    def average(
        self,
        metric: str,
        criteria: Mapping[str, str],
    ) -> tuple[float | None, tuple[StructuredRecord, ...]]:
        """Average a numeric metric over records matching criteria."""
        matched = self.filter_equals(criteria) if criteria else self._records
        values = [record.number(metric) for record in matched]
        numeric_values = [value for value in values if value is not None]
        if not numeric_values:
            return None, tuple(matched)
        return sum(numeric_values) / len(numeric_values), tuple(matched)

    def distinct(
        self,
        field_name: str,
        criteria: Mapping[str, str],
    ) -> tuple[tuple[str, ...], tuple[StructuredRecord, ...]]:
        """Return distinct field values for records matching criteria."""
        matched = self.filter_equals(criteria) if criteria else self._records
        normalized_field = normalize_field_name(field_name)
        values = {
            record.text(normalized_field)
            for record in matched
            if record.text(normalized_field)
        }
        return tuple(sorted(values, key=normalize_value)), tuple(matched)

    def sum(
        self,
        metric: str,
        criteria: Mapping[str, str],
    ) -> tuple[float | None, tuple[StructuredRecord, ...]]:
        """Sum a numeric metric over records matching criteria."""
        matched = self.filter_equals(criteria) if criteria else self._records
        values = [record.number(metric) for record in matched]
        numeric_values = [value for value in values if value is not None]
        if not numeric_values:
            return None, tuple(matched)
        return sum(numeric_values), tuple(matched)

    def minimum(
        self,
        metric: str,
        criteria: Mapping[str, str],
    ) -> tuple[StructuredRecord | None, tuple[StructuredRecord, ...]]:
        """Return the matching record with the smallest numeric metric."""
        matched = self.filter_equals(criteria) if criteria else self._records
        ranked = [record for record in matched if record.number(metric) is not None]
        if not ranked:
            return None, tuple(matched)
        return min(
            ranked,
            key=lambda record: (record.number(metric) or 0.0, _record_sort_key(record.record_id)),
        ), tuple(matched)

    def maximum(
        self,
        metric: str,
        criteria: Mapping[str, str],
    ) -> tuple[StructuredRecord | None, tuple[StructuredRecord, ...]]:
        """Return the matching record with the largest numeric metric."""
        matched = self.filter_equals(criteria) if criteria else self._records
        ranked = [record for record in matched if record.number(metric) is not None]
        if not ranked:
            return None, tuple(matched)
        return max(
            ranked,
            key=lambda record: (record.number(metric) or 0.0, _record_sort_key(record.record_id)),
        ), tuple(matched)


class RuntimeMemoryIndex:
    """In-process memory index used by MCP tools for runtime structured work."""

    def __init__(self) -> None:
        self._contents: list[str] = []

    def add(self, content: str) -> None:
        """Add one raw memory content string."""
        if content and content not in self._contents:
            self._contents.append(content)

    def extend(self, contents: Sequence[str]) -> None:
        """Add multiple raw memory content strings."""
        for content in contents:
            self.add(content)

    def clear(self) -> None:
        """Clear only the runtime read model; persisted memory remains intact."""
        self._contents.clear()

    def contents(self) -> tuple[str, ...]:
        """Return raw memory contents in insertion order."""
        return tuple(self._contents)

    def collection(self) -> CollectionIndex:
        """Return a parsed collection view of current runtime contents."""
        return CollectionIndex.from_chunks(self._contents)


@dataclass(frozen=True)
class RelationEdge:
    """One directed relation edge extracted from text."""

    source: str
    relation: str
    target: str
    evidence: str


class RelationGraph:
    """Small relation graph for deterministic multi-hop continuation."""

    def __init__(self, edges: Sequence[RelationEdge]) -> None:
        self._edges = tuple(edges)

    @classmethod
    def from_chunks(cls, chunks: Sequence[str]) -> RelationGraph:
        """Build a relation graph from raw memory chunks."""
        edges: list[RelationEdge] = []
        for chunk in chunks:
            edges.extend(parse_relation_edges(chunk))
        return cls(edges)

    @property
    def edges(self) -> tuple[RelationEdge, ...]:
        """All relation edges."""
        return self._edges

    def follow(
        self,
        source: str,
        relation: str,
        hops: int,
    ) -> tuple[str, tuple[RelationEdge, ...]] | None:
        """Follow a relation path from source for a fixed number of hops."""
        current = normalize_entity(source)
        used: list[RelationEdge] = []
        relation_key = normalize_value(relation)
        for _ in range(hops):
            edge = self._find_edge(current, relation_key)
            if edge is None:
                return None
            used.append(edge)
            current = normalize_entity(edge.target)
        return used[-1].target, tuple(used)

    def follow_until_stop(
        self,
        source: str,
        relation: str,
        max_hops: int = 4,
    ) -> tuple[str, tuple[RelationEdge, ...]] | None:
        """Follow a relation path until no next edge is available."""
        current = normalize_entity(source)
        used: list[RelationEdge] = []
        relation_key = normalize_value(relation)
        for _ in range(max_hops):
            edge = self._find_edge(current, relation_key)
            if edge is None:
                break
            used.append(edge)
            current = normalize_entity(edge.target)
        if not used:
            return None
        return used[-1].target, tuple(used)

    def _find_edge(self, source: str, relation: str) -> RelationEdge | None:
        for edge in self._edges:
            if (
                normalize_entity(edge.source) == source
                and normalize_value(edge.relation) == relation
            ):
                return edge
        return None


def resolve_collection_evidence(
    question: str,
    chunks: Sequence[str],
    metadata: Mapping[str, Any] | None = None,
) -> CollectionEvidence | None:
    """Resolve exact collection operations from record-like chunks."""
    del metadata
    index = CollectionIndex.from_chunks(chunks)
    if not index.records:
        return None

    criteria = _criteria_from_question(question)
    count_match = re.search(r"how many .+?(?:have|with|where)\s+(.+)", question, re.I)
    if count_match and criteria:
        matched = index.filter_equals(criteria)
        return _collection_evidence(
            strategy=f"structured_count_{next(iter(criteria))}",
            operation="count",
            answer=str(len(matched)),
            records=matched,
            lines=[f"Exact count: {len(matched)} records matching {_criteria_text(criteria)}."],
            metadata={"criteria": dict(criteria)},
        )

    filter_match = re.search(r"\b(list|show|find)\b.+\b(where|with)\b", question, re.I)
    if filter_match and criteria:
        matched = index.filter_equals(criteria)
        names = [record.record_id for record in matched]
        answer = ", ".join(names) if names else "none"
        return _collection_evidence(
            strategy="structured_filter_records",
            operation="filter",
            answer=answer,
            records=matched,
            lines=[f"Exact filter: {_criteria_text(criteria)}.", f"Answer: {answer}."],
            metadata={"criteria": dict(criteria)},
        )

    natural_filter = _employee_style_filter(question)
    if natural_filter:
        matched = index.filter_equals(natural_filter)
        names = [
            record.record_id
            for record in sorted(matched, key=lambda record: _record_sort_key(record.record_id))
        ]
        answer = ", ".join(names) if names else "none"
        return _collection_evidence(
            strategy="structured_filter_records",
            operation="filter",
            answer=answer,
            records=matched,
            lines=[f"Exact filter: {_criteria_text(natural_filter)}.", f"Answer: {answer}."],
            metadata={"criteria": dict(natural_filter)},
        )

    top_match = re.search(r"top\s+(\d+).+?\bby\s+([A-Za-z_ ]+?)(?:\?|\.|$)", question, re.I)
    if top_match:
        k = int(top_match.group(1))
        metric = _best_field_name(index, top_match.group(2), numeric=True)
        ranked = index.top_k(metric, k)
        answer = ", ".join(record.record_id for record in ranked)
        return _collection_evidence(
            strategy=f"structured_top_k_{metric}",
            operation="top_k",
            answer=answer,
            records=ranked,
            lines=[
                f"Exact top {k} by {metric}: {answer}.",
                *_record_metric_lines(ranked, metric),
            ],
            metadata={"metric": metric, "k": k},
        )

    average = _average_request(question, index)
    if average is not None:
        metric, average_criteria = average
        value, matched = index.average(metric, average_criteria)
        answer = f"{value:.1f}" if value is not None else "0.0"
        return _collection_evidence(
            strategy=f"structured_average_{metric}",
            operation="aggregate",
            answer=answer,
            records=matched,
            lines=[
                f"Exact average: {metric} = {answer} for {_criteria_text(average_criteria)}.",
                *_record_metric_lines(matched, metric),
            ],
            metadata={"metric": metric, "criteria": dict(average_criteria)},
        )

    total = _sum_request(question, index)
    if total is not None:
        metric, sum_criteria = total
        value, matched = index.sum(metric, sum_criteria)
        answer = f"{value:.1f}" if value is not None else "0.0"
        return _collection_evidence(
            strategy=f"structured_sum_{metric}",
            operation="sum",
            answer=answer,
            records=matched,
            lines=[
                f"Exact sum: {metric} = {answer} for {_criteria_text(sum_criteria)}.",
                *_record_metric_lines(matched, metric),
            ],
            metadata={"metric": metric, "criteria": dict(sum_criteria)},
        )

    extrema = _extrema_request(question, index)
    if extrema is not None:
        operation, metric, extrema_criteria = extrema
        record, matched = (
            index.minimum(metric, extrema_criteria)
            if operation == "min"
            else index.maximum(metric, extrema_criteria)
        )
        if record is None:
            return None
        return _collection_evidence(
            strategy=f"structured_{operation}_{metric}",
            operation=operation,
            answer=record.record_id,
            records=(record,),
            lines=[
                f"Exact {operation}: {record.record_id} has {metric}={record.text(metric)}.",
            ],
            metadata={
                "metric": metric,
                "criteria": dict(extrema_criteria),
                "candidate_count": len(matched),
            },
        )

    distinct = _distinct_request(question, index)
    if distinct is not None:
        field_name, distinct_criteria = distinct
        values, matched = index.distinct(field_name, distinct_criteria)
        answer = ", ".join(values) if values else "none"
        return _collection_evidence(
            strategy=f"structured_distinct_{field_name}",
            operation="distinct",
            answer=answer,
            records=matched,
            lines=[
                f"Exact distinct {field_name}: {answer}.",
            ],
            metadata={"field": field_name, "criteria": dict(distinct_criteria)},
        )

    comparison = _comparison_request(question, index)
    if comparison is not None:
        group_field, metric, value_a, value_b = comparison
        avg_a, records_a = index.average(metric, {group_field: value_a})
        avg_b, records_b = index.average(metric, {group_field: value_b})
        if avg_a is None or avg_b is None:
            return None
        winner = value_a if avg_a >= avg_b else value_b
        matched = (*records_a, *records_b)
        return _collection_evidence(
            strategy=f"structured_compare_{group_field}_{metric}",
            operation="compare",
            answer=winner,
            records=matched,
            lines=[
                f"{value_a}: average_{metric}={avg_a:.1f} from {len(records_a)} records.",
                f"{value_b}: average_{metric}={avg_b:.1f} from {len(records_b)} records.",
                f"Answer: {winner}.",
            ],
            metadata={
                "group_field": group_field,
                "metric": metric,
                "value_a": value_a,
                "value_b": value_b,
            },
        )

    return None


def resolve_relation_evidence(
    question: str,
    chunks: Sequence[str],
    metadata: Mapping[str, Any] | None = None,
) -> CollectionEvidence | None:
    """Resolve deterministic relation-chain questions from relation facts."""
    del metadata
    graph = RelationGraph.from_chunks(chunks)
    if not graph.edges:
        return None

    relation = _relation_from_question(question, graph.edges)
    if not relation:
        return None
    source = _source_entity_for_relation_question(question, graph.edges)
    if not source:
        return None
    if "chain" in question.lower():
        followed = graph.follow_until_stop(source, relation)
    else:
        followed = graph.follow(source, relation, _relation_hops(question, relation))
    if followed is None:
        return None
    answer, edges = followed
    return CollectionEvidence(
        strategy=f"relation_graph_{normalize_field_name(relation)}",
        operation="relation_path",
        answer=answer,
        supporting_evidence=tuple(
            f"{edge.source} --{edge.relation}--> {edge.target}" for edge in edges
        ),
        metadata={
            "planner": "graph",
            "deterministic_answer": True,
            "skip_semantic_queries": True,
            "relation": relation,
            "source": source,
            "hops": len(edges),
        },
    )


def collection_evidence_to_dict(evidence: CollectionEvidence) -> dict[str, Any]:
    """Convert collection evidence to a serializable payload."""
    return {
        "strategy": evidence.strategy,
        "operation": evidence.operation,
        "answer": evidence.answer,
        "matched_records": [
            {"id": record.record_id, "fields": dict(record.fields), "raw": record.raw}
            for record in evidence.matched_records
        ],
        "supporting_evidence": list(evidence.supporting_evidence),
        "metadata": dict(evidence.metadata),
    }


def parse_records(chunk: str) -> tuple[StructuredRecord, ...]:
    """Parse one or more record-like memory chunks."""
    records = _parse_jsonl_records(chunk)
    if records:
        return records

    records = _parse_markdown_table_records(chunk)
    if records:
        return records

    record = parse_record(chunk)
    return (record,) if record is not None else ()


def parse_record(chunk: str) -> StructuredRecord | None:
    """Parse one record-like memory chunk."""
    employee = _parse_employee_record(chunk)
    if employee is not None:
        return employee

    fields = _parse_key_value_fields(chunk)
    if not fields:
        return None
    record_id = _record_id_from_fields(fields, chunk)
    return StructuredRecord(record_id=record_id, fields=fields, raw=chunk)


def _parse_jsonl_records(chunk: str) -> tuple[StructuredRecord, ...]:
    records: list[StructuredRecord] = []
    for line in chunk.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{") or not stripped.endswith("}"):
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        fields = _json_fields(payload)
        if not fields:
            continue
        records.append(
            StructuredRecord(
                record_id=_record_id_from_fields(fields, stripped),
                fields=fields,
                raw=stripped,
            )
        )
    return tuple(records)


def _json_fields(payload: Mapping[str, object]) -> dict[str, Scalar]:
    fields: dict[str, Scalar] = {}
    for key, value in payload.items():
        if isinstance(value, bool):
            fields[normalize_field_name(key)] = str(value).lower()
        elif isinstance(value, int | float):
            fields[normalize_field_name(key)] = float(value)
        elif isinstance(value, str):
            normalized_key = normalize_field_name(key)
            fields[normalized_key] = _parse_field_scalar(normalized_key, value)
    return fields


def _parse_markdown_table_records(chunk: str) -> tuple[StructuredRecord, ...]:
    lines = [line.strip() for line in chunk.splitlines() if line.strip().startswith("|")]
    if len(lines) < 3:
        return ()
    header = _markdown_cells(lines[0])
    separator = _markdown_cells(lines[1])
    if not header or not _is_markdown_separator(separator):
        return ()

    records: list[StructuredRecord] = []
    for line in lines[2:]:
        cells = _markdown_cells(line)
        if len(cells) != len(header):
            continue
        fields = {
            normalize_field_name(key): _parse_field_scalar(normalize_field_name(key), value)
            for key, value in zip(header, cells, strict=True)
        }
        raw = " | ".join(cells)
        records.append(
            StructuredRecord(
                record_id=_record_id_from_fields(fields, raw),
                fields=fields,
                raw=line,
            )
        )
    return tuple(records)


def _markdown_cells(line: str) -> tuple[str, ...]:
    return tuple(cell.strip() for cell in line.strip().strip("|").split("|"))


def _is_markdown_separator(cells: Sequence[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def parse_relation_edges(chunk: str) -> tuple[RelationEdge, ...]:
    """Parse relation edges from a text chunk."""
    edges: list[RelationEdge] = []
    advisor_match = re.fullmatch(r"(.+?)'s doctoral advisor was (.+?) at (.+)", chunk)
    if advisor_match:
        source, target, _place = advisor_match.groups()
        edges.append(
            RelationEdge(
                source=source.strip(),
                relation="doctoral advisor",
                target=target.strip(),
                evidence=chunk,
            )
        )

    worked_with_match = re.fullmatch(r"(.+?) worked with (.+?) at (.+)", chunk)
    if worked_with_match:
        source, target, _place = worked_with_match.groups()
        edges.append(
            RelationEdge(
                source=source.strip(),
                relation="worked with",
                target=target.strip(),
                evidence=chunk,
            )
        )

    extended_match = re.fullmatch(
        r"(.+?) discovered .+? which was later extended by (.+)",
        chunk,
    )
    if extended_match:
        source, target = extended_match.groups()
        edges.append(
            RelationEdge(
                source=source.strip(),
                relation="extended",
                target=target.strip(),
                evidence=chunk,
            )
        )

    arrow_match = re.fullmatch(r"(.+?)\s*->\s*(.+?)\s*->\s*(.+)", chunk)
    if arrow_match:
        source, relation, target = arrow_match.groups()
        edges.append(
            RelationEdge(
                source=source.strip(),
                relation=relation.strip(),
                target=target.strip(),
                evidence=chunk,
            )
        )
    return tuple(edges)


def normalize_field_name(value: str) -> str:
    """Normalize a field or metric name."""
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    aliases = {
        "score": "performance_score",
        "performance": "performance_score",
        "performance_score": "performance_score",
        "years": "years_experience",
        "years_of_experience": "years_experience",
        "experience": "years_experience",
        "department_name": "department",
    }
    return aliases.get(normalized, normalized)


def normalize_value(value: object) -> str:
    """Normalize a scalar value for equality checks."""
    return " ".join(str(value).strip().lower().split())


def normalize_entity(value: str) -> str:
    """Normalize an entity name for graph lookup."""
    return normalize_value(value).replace("'s", "")


def _collection_evidence(
    *,
    strategy: str,
    operation: str,
    answer: str,
    records: Sequence[StructuredRecord],
    lines: Sequence[str],
    metadata: Mapping[str, Any],
) -> CollectionEvidence:
    return CollectionEvidence(
        strategy=strategy,
        operation=operation,
        answer=answer,
        matched_records=tuple(records),
        supporting_evidence=tuple(lines),
        metadata={
            "planner": "structured",
            "deterministic_answer": True,
            "skip_semantic_queries": True,
            "collection_record_count": len(records),
            **dict(metadata),
        },
    )


def _parse_employee_record(chunk: str) -> StructuredRecord | None:
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
    fields: dict[str, Scalar] = {
        "name": name,
        "department": department,
        "location": location,
        "status": status,
        "years_experience": float(years_experience),
        "project": project,
        "skills": skills,
        "performance_score": float(performance_score),
        "salary_band": salary_band,
    }
    return StructuredRecord(record_id=name, fields=fields, raw=chunk)


def _parse_key_value_fields(chunk: str) -> dict[str, Scalar]:
    fields: dict[str, Scalar] = {}
    parts = re.split(r"[|\n;]+", chunk)
    if len(parts) == 1:
        parts = re.split(r"\.\s+", chunk)
    for part in parts:
        match = re.search(
            r"\b([A-Za-z][A-Za-z0-9 _-]{1,40})\s*(?:=|:)\s*([^|;\n.]+)",
            part,
        )
        if not match:
            continue
        key, value = match.groups()
        fields[normalize_field_name(key)] = _parse_scalar(value)
    return fields


def _parse_scalar(value: str) -> Scalar:
    stripped = value.strip().strip("'\"")
    number = _parse_number(stripped)
    return number if number is not None else stripped


def _parse_field_scalar(field_name: str, value: str) -> Scalar:
    if field_name in {"id", "name", "title", "record"}:
        return value.strip().strip("'\"")
    return _parse_scalar(value)


def _parse_number(value: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else None


def _format_scalar(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _record_id_from_fields(fields: Mapping[str, Scalar], chunk: str) -> str:
    for field_name in ("name", "id", "title", "record"):
        value = fields.get(field_name)
        if value:
            return _format_scalar(value)
    prefix = re.split(r"[|:;\n.]", chunk, maxsplit=1)[0].strip()
    return prefix[:80] if prefix else "record"


def _criteria_from_question(question: str) -> dict[str, str]:
    criteria: dict[str, str] = {}
    single_quoted = _criteria_pairs(
        question,
        (r"\b(?:have|with|where)\s+([A-Za-z_][A-Za-z0-9_ ]{1,40})\s*=\s*'([^']+)'",),
    )
    if not single_quoted:
        single_quoted = _criteria_pairs(
            question,
            (r"\b([A-Za-z_][A-Za-z0-9_ ]{1,40})\s*=\s*'([^']+)'",),
        )
    for field_name, value in single_quoted:
        criteria[normalize_field_name(field_name)] = value
    double_quoted = _criteria_pairs(
        question,
        (r'\b(?:have|with|where)\s+([A-Za-z_][A-Za-z0-9_ ]{1,40})\s*=\s*"([^"]+)"',),
    )
    if not double_quoted:
        double_quoted = _criteria_pairs(
            question,
            (r'\b([A-Za-z_][A-Za-z0-9_ ]{1,40})\s*=\s*"([^"]+)"',),
        )
    for field_name, value in double_quoted:
        criteria[normalize_field_name(field_name)] = value
    return criteria


def _employee_style_filter(question: str) -> dict[str, str]:
    match = re.search(
        r"in the (.+?) department who are based in (.+?)(?:\.|\?|$)",
        question,
        re.I,
    )
    if not match:
        return {}
    department, location = match.groups()
    return {"department": department, "location": location}


def _average_request(
    question: str,
    index: CollectionIndex,
) -> tuple[str, dict[str, str]] | None:
    average_match = re.search(r"average\s+(.+?)\s+for", question, re.I)
    if not average_match:
        return None
    metric = _best_field_name(index, average_match.group(1), numeric=True)
    criteria = _criteria_from_question(question)
    department_match = re.search(r"in the (.+?) department", question, re.I)
    if department_match:
        criteria["department"] = department_match.group(1)
    return metric, criteria


def _sum_request(
    question: str,
    index: CollectionIndex,
) -> tuple[str, dict[str, str]] | None:
    match = re.search(r"\b(?:sum|total)\s+(.+?)(?:\s+for|\s+where|\?|$)", question, re.I)
    if not match:
        return None
    metric = _best_field_name(index, match.group(1), numeric=True)
    return metric, _criteria_from_question(question)


def _extrema_request(
    question: str,
    index: CollectionIndex,
) -> tuple[str, str, dict[str, str]] | None:
    match = re.search(
        r"\b(lowest|smallest|min(?:imum)?|highest|largest|max(?:imum)?)"
        r"\s+(.+?)(?:\s+for|\s+where|\?|$)",
        question,
        re.I,
    )
    if not match:
        return None
    operation_word, metric_request = match.groups()
    operation = (
        "min"
        if operation_word.lower() in {"lowest", "smallest", "min", "minimum"}
        else "max"
    )
    metric = _best_field_name(index, metric_request, numeric=True)
    return operation, metric, _criteria_from_question(question)


def _distinct_request(
    question: str,
    index: CollectionIndex,
) -> tuple[str, dict[str, str]] | None:
    match = re.search(r"\b(?:distinct|unique)\s+(.+?)(?:\s+for|\s+where|\?|$)", question, re.I)
    if not match:
        return None
    field_name = _best_field_name(index, match.group(1), numeric=False)
    return field_name, _criteria_from_question(question)


def _comparison_request(
    question: str,
    index: CollectionIndex,
) -> tuple[str, str, str, str] | None:
    match = re.search(
        r"higher average\s+(.+?),\s+(.+?)\s+or\s+(.+?)(?:\?|$)",
        question,
        re.I,
    )
    if not match:
        return None
    metric = _best_field_name(index, match.group(1), numeric=True)
    return "department", metric, match.group(2).strip(), match.group(3).strip()


def _best_field_name(index: CollectionIndex, requested: str, *, numeric: bool = False) -> str:
    requested_name = normalize_field_name(requested)
    candidates = index.numeric_field_names if numeric else index.field_names
    if requested_name in candidates:
        return requested_name
    singular_name = requested_name[:-1] if requested_name.endswith("s") else requested_name
    if singular_name in candidates:
        return singular_name
    requested_tokens = set(requested_name.split("_"))
    best = ""
    best_overlap = 0
    for candidate in candidates:
        overlap = len(requested_tokens & set(candidate.split("_")))
        if overlap > best_overlap:
            best = candidate
            best_overlap = overlap
    return best or requested_name


def _criteria_text(criteria: Mapping[str, str]) -> str:
    if not criteria:
        return "all records"
    return ", ".join(f"{field}={value}" for field, value in criteria.items())


def _record_metric_lines(records: Sequence[StructuredRecord], metric: str) -> list[str]:
    return [f"{record.record_id}: {metric}={record.text(metric)}" for record in records]


def _record_sort_key(record_id: str) -> tuple[str, int, str]:
    match = re.search(r"^(.*?)(\d+)$", record_id)
    if not match:
        return record_id, 0, record_id
    prefix, number = match.groups()
    return prefix, int(number), record_id


def _record_matches(record: StructuredRecord, criteria: Mapping[str, str]) -> bool:
    return all(
        normalize_value(record.text(field_name)) == target
        for field_name, target in criteria.items()
    )


def _criteria_pairs(
    question: str,
    patterns: Sequence[str],
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for pattern in patterns:
        for field_name, value in re.findall(pattern, question, re.I):
            clean_field = re.sub(
                r"^.*\b(?:have|with|where)\s+",
                "",
                field_name,
                flags=re.I,
            )
            pairs.append((clean_field.strip(), value.strip()))
    return pairs


def _relation_from_question(question: str, edges: Sequence[RelationEdge]) -> str:
    lowered = question.lower()
    edge_relations = tuple(edge.relation for edge in edges)
    for relation in (
        *edge_relations,
        "doctoral advisor",
        "worked with",
        "reports to",
        "parent of",
        "cites",
        "extended",
    ):
        relation_key = relation.lower()
        singular_key = relation_key[:-1] if relation_key.endswith("s") else relation_key
        if relation_key in lowered or singular_key in lowered:
            return relation
    return ""


def _relation_hops(question: str, relation: str) -> int:
    lowered = question.lower()
    relation_key = relation.lower()
    mentions = lowered.count(relation_key)
    if mentions:
        return mentions
    singular_key = relation_key[:-1] if relation_key.endswith("s") else relation_key
    return max(1, lowered.count(singular_key))


def _source_entity_for_relation_question(
    question: str,
    edges: Sequence[RelationEdge],
) -> str:
    normalized_question = normalize_entity(question)
    for edge in edges:
        if normalize_entity(edge.source) in normalized_question:
            return edge.source
    return ""
