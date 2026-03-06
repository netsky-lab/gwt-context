"""Tests for CompetitionEngine."""

from gwt_context.domain.competition import CompetitionEngine
from gwt_context.domain.models import Goal, MemoryItem, MemoryType
from gwt_context.domain.specialists import (
    RelevanceSpecialist,
    RecencySpecialist,
    StructuralLinkageSpecialist,
    create_default_specialists,
)
from gwt_context.domain.workspace import GlobalWorkspace


def _item(id: str, embedding: list[float] | None = None, **kw) -> MemoryItem:
    return MemoryItem(
        id=id, content=f"content of {id}",
        memory_type=MemoryType.SEMANTIC,
        embedding=embedding, **kw,
    )


class TestCompetitionEngine:
    def test_empty_candidates(self):
        engine = CompetitionEngine(specialists=create_default_specialists())
        ws = GlobalWorkspace(capacity=3)
        result = engine.run_competition([], [], ws)
        assert result.winners == []
        assert result.evicted == []

    def test_fills_empty_workspace(self):
        engine = CompetitionEngine(specialists=create_default_specialists())
        ws = GlobalWorkspace(capacity=2)
        candidates = [_item("a", [1, 0, 0]), _item("b", [0, 1, 0]), _item("c", [0, 0, 1])]
        result = engine.run_competition(candidates, [], ws)
        # Should pick 2 winners for 2 slots
        assert len(result.winners) == 2
        assert len(result.evicted) == 0

    def test_evicts_weaker_items(self):
        # Use only relevance specialist for deterministic test
        rel = RelevanceSpecialist()
        rel.weight = 1.0
        engine = CompetitionEngine(specialists=[rel], goal_modulation_strength=0.0)

        ws = GlobalWorkspace(capacity=1)
        weak = _item("weak", [0, 0, 1])
        ws.admit(weak)

        goal = Goal(description="goal", embedding=[1, 0, 0])
        strong = _item("strong", [1, 0, 0])

        result = engine.run_competition([strong], [goal], ws)
        assert any(w.id == "strong" for w in result.winners)
        assert any(e.id == "weak" for e in result.evicted)

    def test_goal_modulation_boosts(self):
        rel = RelevanceSpecialist()
        rel.weight = 1.0
        engine = CompetitionEngine(specialists=[rel], goal_modulation_strength=0.5)
        ws = GlobalWorkspace(capacity=3)
        goal = Goal(description="goal", embedding=[1, 0, 0])

        item = _item("x", [1, 0, 0])
        score = engine.score_item(item, [goal], ws)
        # With perfect relevance, goal modulation should boost significantly
        assert score > 0.9

    def test_skips_items_already_in_workspace(self):
        engine = CompetitionEngine(specialists=create_default_specialists())
        ws = GlobalWorkspace(capacity=3)
        item = _item("existing")
        ws.admit(item)

        result = engine.run_competition([item], [], ws)
        # Should not appear as winner again
        assert item.id not in {w.id for w in result.winners}

    def test_score_item(self):
        engine = CompetitionEngine(specialists=create_default_specialists())
        ws = GlobalWorkspace(capacity=3)
        item = _item("x", [1, 0, 0])
        score = engine.score_item(item, [], ws)
        assert 0 <= score <= 1
