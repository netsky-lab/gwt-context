"""Tests for structured collection and relation evidence."""

from gwt_context.application.structured import (
    CollectionIndex,
    RelationGraph,
    RuntimeMemoryIndex,
    parse_record,
    parse_records,
    resolve_collection_evidence,
    resolve_relation_evidence,
)


def test_parse_record_accepts_generic_key_value_chunks() -> None:
    record = parse_record(
        "Idea-001 | type=twitter | topic=GWT | score=9 | status=ready"
    )

    assert record is not None
    assert record.record_id == "Idea-001"
    assert record.text("topic") == "GWT"
    assert record.number("score") == 9.0


def test_collection_index_filters_sorts_and_averages_generic_records() -> None:
    index = CollectionIndex.from_chunks(
        [
            "Idea-001 | type=twitter | topic=GWT | score=9 | status=ready",
            "Idea-002 | type=twitter | topic=memory | score=7 | status=draft",
            "Idea-003 | type=note | topic=GWT | score=5 | status=ready",
        ]
    )

    ready = index.filter_equals({"status": "ready"})
    top = index.top_k("score", 2)
    average, matched = index.average("score", {"type": "twitter"})

    assert [record.record_id for record in ready] == ["Idea-001", "Idea-003"]
    assert [record.record_id for record in top] == ["Idea-001", "Idea-002"]
    assert average == 8.0
    assert [record.record_id for record in matched] == ["Idea-001", "Idea-002"]


def test_parse_records_accepts_jsonl_and_markdown_tables() -> None:
    jsonl = "\n".join(
        [
            '{"id": "Idea-001", "topic": "GWT", "score": 9}',
            '{"id": "Idea-002", "topic": "memory", "score": 7}',
        ]
    )
    table = "\n".join(
        [
            "| id | topic | score |",
            "| --- | --- | --- |",
            "| Idea-003 | GWT | 5 |",
            "| Idea-004 | agents | 8 |",
        ]
    )

    parsed = (*parse_records(jsonl), *parse_records(table))

    assert [record.record_id for record in parsed] == [
        "Idea-001",
        "Idea-002",
        "Idea-003",
        "Idea-004",
    ]
    assert parsed[2].text("topic") == "GWT"
    assert parsed[3].number("score") == 8.0


def test_collection_index_aggregates_distinct_sum_min_and_max() -> None:
    index = CollectionIndex.from_chunks(
        [
            '{"id": "Idea-001", "topic": "GWT", "score": 9, "status": "ready"}',
            '{"id": "Idea-002", "topic": "memory", "score": 7, "status": "draft"}',
            '{"id": "Idea-003", "topic": "GWT", "score": 5, "status": "ready"}',
        ]
    )

    values, distinct_records = index.distinct("topic", {})
    total, ready_records = index.sum("score", {"status": "ready"})
    minimum, _ = index.minimum("score", {})
    maximum, _ = index.maximum("score", {})

    assert values == ("GWT", "memory")
    assert [record.record_id for record in distinct_records] == [
        "Idea-001",
        "Idea-002",
        "Idea-003",
    ]
    assert total == 14.0
    assert [record.record_id for record in ready_records] == ["Idea-001", "Idea-003"]
    assert minimum is not None
    assert minimum.record_id == "Idea-003"
    assert maximum is not None
    assert maximum.record_id == "Idea-001"


def test_resolve_collection_evidence_counts_and_ranks_generic_records() -> None:
    chunks = [
        "Idea-001 | type=twitter | topic=GWT | score=9 | status=ready",
        "Idea-002 | type=twitter | topic=memory | score=7 | status=draft",
    ]

    count = resolve_collection_evidence(
        "How many ideas have status = 'ready'?",
        chunks,
    )
    top = resolve_collection_evidence("Who are the top 1 ideas by score?", chunks)

    assert count is not None
    assert count.operation == "count"
    assert count.answer == "1"
    assert top is not None
    assert top.operation == "top_k"
    assert top.answer == "Idea-001"


def test_resolve_collection_evidence_handles_jsonl_aggregates() -> None:
    chunks = [
        '{"id": "Idea-001", "topic": "GWT", "score": 9, "status": "ready"}',
        '{"id": "Idea-002", "topic": "memory", "score": 7, "status": "draft"}',
    ]

    total = resolve_collection_evidence("What is the total score?", chunks)
    distinct = resolve_collection_evidence("What are the distinct topics?", chunks)

    assert total is not None
    assert total.operation == "sum"
    assert total.answer == "16.0"
    assert distinct is not None
    assert distinct.operation == "distinct"
    assert distinct.answer == "GWT, memory"


def test_relation_graph_follows_runtime_edges() -> None:
    graph = RelationGraph.from_chunks(
        [
            "Paper Alpha -> cites -> Paper Beta",
            "Paper Beta -> cites -> Paper Gamma",
        ]
    )

    followed = graph.follow("Paper Alpha", "cites", 2)

    assert followed is not None
    answer, edges = followed
    assert answer == "Paper Gamma"
    assert [edge.source for edge in edges] == ["Paper Alpha", "Paper Beta"]


def test_resolve_relation_evidence_uses_edge_relation_names() -> None:
    evidence = resolve_relation_evidence(
        "What does Paper Alpha cite cite?",
        [
            "Paper Alpha -> cites -> Paper Beta",
            "Paper Beta -> cites -> Paper Gamma",
        ],
    )

    assert evidence is not None
    assert evidence.strategy == "relation_graph_cites"
    assert evidence.answer == "Paper Gamma"
    assert evidence.metadata["hops"] == 2


def test_resolve_relation_evidence_accepts_worked_with_sentences() -> None:
    evidence = resolve_relation_evidence(
        "Who worked with the person that Ada Lovelace worked with?",
        [
            "Ada Lovelace worked with Grace Hopper at MIT",
            "Grace Hopper worked with Alan Turing at Cambridge",
        ],
    )

    assert evidence is not None
    assert evidence.strategy == "relation_graph_worked_with"
    assert evidence.answer == "Alan Turing"


def test_resolve_relation_evidence_accepts_extended_by_sentences() -> None:
    evidence = resolve_relation_evidence(
        "Who extended the work of the person who extended Ada Lovelace's work?",
        [
            "Ada Lovelace discovered symbolic computation which was later extended by Grace Hopper",
            "Grace Hopper discovered compilers which was later extended by Alan Turing",
        ],
    )

    assert evidence is not None
    assert evidence.strategy == "relation_graph_extended"
    assert evidence.answer == "Alan Turing"


def test_runtime_memory_index_deduplicates_and_exposes_collection_view() -> None:
    index = RuntimeMemoryIndex()
    index.add("Idea-001 | type=twitter | score=9")
    index.add("Idea-001 | type=twitter | score=9")

    assert index.contents() == ("Idea-001 | type=twitter | score=9",)
    assert index.collection().records[0].record_id == "Idea-001"
