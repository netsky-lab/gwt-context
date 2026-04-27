"""Real-ish workload checks for runtime structured attention.

The fixtures model project notes, tweet drafts, and research references rather
than benchmark-only employee records.
"""

from gwt_context.application.attention import GenericEvidenceResolver


def test_project_note_workload_resolves_collection_selection() -> None:
    chunks = [
        "Idea-001 | type=twitter | topic=GWT | score=9 | status=ready",
        "Idea-002 | type=twitter | topic=memory | score=7 | status=draft",
        "Idea-003 | type=design-note | topic=GWT | score=8 | status=ready",
    ]

    count = GenericEvidenceResolver(planner="structured").resolve(
        "How many ideas have status = 'ready'?",
        chunks,
        {},
    )
    top = GenericEvidenceResolver(planner="structured").resolve(
        "Who are the top 2 ideas by score?",
        chunks,
        {},
    )

    assert count.strategy == "structured_count_status"
    assert count.answer == "2"
    assert top.strategy == "structured_top_k_performance_score"
    assert top.answer == "Idea-001, Idea-003"


def test_research_reference_workload_resolves_relation_path() -> None:
    chunks = [
        "Paper Alpha -> cites -> Paper Beta",
        "Paper Beta -> cites -> Paper Gamma",
        "Paper Gamma | type=paper | topic=global workspace | year=2025",
    ]

    plan = GenericEvidenceResolver(planner="graph").resolve(
        "What does Paper Alpha cite cite?",
        chunks,
        {},
    )

    assert plan.strategy == "relation_graph_cites"
    assert plan.answer == "Paper Gamma"
    assert plan.metadata["hops"] == 2
