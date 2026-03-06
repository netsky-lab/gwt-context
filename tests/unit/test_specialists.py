"""Tests for specialist processors."""

import math
from datetime import datetime, timedelta, timezone

from gwt_context.domain.models import Goal, MemoryItem, MemoryType
from gwt_context.domain.specialists import (
    FrequencySpecialist,
    GoalLinkageSpecialist,
    NoveltySpecialist,
    RecencySpecialist,
    RelevanceSpecialist,
    StructuralLinkageSpecialist,
    cosine_similarity,
    create_default_specialists,
)
from gwt_context.domain.workspace import GlobalWorkspace


def _make_item(**kwargs) -> MemoryItem:
    defaults = {"id": "t1", "content": "test", "memory_type": MemoryType.SEMANTIC}
    defaults.update(kwargs)
    return MemoryItem(**defaults)


def _make_goal(**kwargs) -> Goal:
    defaults = {"description": "test goal"}
    defaults.update(kwargs)
    return Goal(**defaults)


class TestCosine:
    def test_identical(self):
        v = [1.0, 0.0, 0.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal(self):
        assert abs(cosine_similarity([1, 0], [0, 1])) < 1e-6

    def test_zero_vector(self):
        assert cosine_similarity([0, 0], [1, 1]) == 0.0


class TestRelevanceSpecialist:
    def test_no_goals(self):
        s = RelevanceSpecialist()
        item = _make_item(embedding=[1.0, 0.0])
        assert s.score(item, [], GlobalWorkspace()) == 0.0

    def test_no_embedding(self):
        s = RelevanceSpecialist()
        item = _make_item()
        goal = _make_goal(embedding=[1.0, 0.0])
        assert s.score(item, [goal], GlobalWorkspace()) == 0.0

    def test_high_similarity(self):
        s = RelevanceSpecialist()
        item = _make_item(embedding=[1.0, 0.0, 0.0])
        goal = _make_goal(embedding=[1.0, 0.0, 0.0])
        score = s.score(item, [goal], GlobalWorkspace())
        assert score > 0.9

    def test_goal_priority_scales(self):
        s = RelevanceSpecialist()
        item = _make_item(embedding=[1.0, 0.5, 0.0])
        goal_low = _make_goal(embedding=[1.0, 0.5, 0.0], priority=0.5)
        goal_high = _make_goal(embedding=[1.0, 0.5, 0.0], priority=1.0)
        score_low = s.score(item, [goal_low], GlobalWorkspace())
        score_high = s.score(item, [goal_high], GlobalWorkspace())
        assert score_high > score_low


class TestRecencySpecialist:
    def test_fresh_item(self):
        s = RecencySpecialist()
        item = _make_item()
        score = s.score(item, [], GlobalWorkspace())
        assert score > 0.99

    def test_old_item(self):
        s = RecencySpecialist(half_life_hours=1.0)
        item = _make_item()
        item.last_accessed = datetime.now(timezone.utc) - timedelta(hours=5)
        score = s.score(item, [], GlobalWorkspace())
        assert score < 0.1


class TestFrequencySpecialist:
    def test_zero_access(self):
        s = FrequencySpecialist()
        item = _make_item()
        assert s.score(item, [], GlobalWorkspace()) == 0.0

    def test_max_access(self):
        s = FrequencySpecialist(max_count=10)
        item = _make_item()
        item.access_count = 15
        assert s.score(item, [], GlobalWorkspace()) == 1.0


class TestStructuralLinkageSpecialist:
    def test_no_links(self):
        s = StructuralLinkageSpecialist()
        item = _make_item()
        assert s.score(item, [], GlobalWorkspace()) == 0.0

    def test_linked_to_workspace(self):
        s = StructuralLinkageSpecialist()
        ws = GlobalWorkspace(capacity=3)
        ws_item = _make_item(id="ws1")
        ws.admit(ws_item)

        item = _make_item(id="candidate", linked_ids=["ws1", "other"])
        score = s.score(item, [], ws)
        assert score == 0.5  # 1 of 2 links in workspace

    def test_all_links_in_workspace(self):
        s = StructuralLinkageSpecialist()
        ws = GlobalWorkspace(capacity=3)
        ws.admit(_make_item(id="ws1"))
        ws.admit(_make_item(id="ws2"))

        item = _make_item(id="cand", linked_ids=["ws1", "ws2"])
        assert s.score(item, [], ws) == 1.0


class TestGoalLinkageSpecialist:
    def test_no_links(self):
        s = GoalLinkageSpecialist()
        item = _make_item()
        goal = _make_goal(embedding=[1.0, 0.0, 0.0])
        assert s.score(item, [goal], GlobalWorkspace()) == 0.0

    def test_no_goals(self):
        s = GoalLinkageSpecialist()
        ws = GlobalWorkspace(capacity=3)
        ws.admit(_make_item(id="ws1", embedding=[1.0, 0.0, 0.0]))
        item = _make_item(id="cand", linked_ids=["ws1"])
        assert s.score(item, [], ws) == 0.0

    def test_linked_to_goal_relevant_item(self):
        """Link to a workspace item that IS relevant to goal → high score."""
        s = GoalLinkageSpecialist()
        ws = GlobalWorkspace(capacity=3)
        # ws_item embedding matches goal
        ws_item = _make_item(id="ws1", embedding=[1.0, 0.0, 0.0])
        ws.admit(ws_item)

        goal = _make_goal(embedding=[1.0, 0.0, 0.0])
        item = _make_item(id="cand", linked_ids=["ws1"])
        score = s.score(item, [goal], ws)
        assert score > 0.9  # Linked item is very relevant to goal

    def test_linked_to_goal_irrelevant_item(self):
        """Link to a workspace item that is NOT relevant to goal → low score."""
        s = GoalLinkageSpecialist()
        ws = GlobalWorkspace(capacity=3)
        # ws_item embedding is orthogonal to goal
        ws_item = _make_item(id="ws1", embedding=[0.0, 1.0, 0.0])
        ws.admit(ws_item)

        goal = _make_goal(embedding=[1.0, 0.0, 0.0])
        item = _make_item(id="cand", linked_ids=["ws1"])
        score = s.score(item, [goal], ws)
        assert score < 0.1  # Linked item is irrelevant to goal

    def test_mixed_relevance_links(self):
        """Links to both relevant and irrelevant items → medium score."""
        s = GoalLinkageSpecialist()
        ws = GlobalWorkspace(capacity=3)
        ws.admit(_make_item(id="relevant", embedding=[1.0, 0.0, 0.0]))
        ws.admit(_make_item(id="irrelevant", embedding=[0.0, 0.0, 1.0]))

        goal = _make_goal(embedding=[1.0, 0.0, 0.0])
        item = _make_item(id="cand", linked_ids=["relevant", "irrelevant"])
        score = s.score(item, [goal], ws)
        # Average of high (~1.0) and low (~0.0)
        assert 0.3 < score < 0.7


class TestNoveltySpecialist:
    def test_empty_workspace(self):
        s = NoveltySpecialist()
        item = _make_item(embedding=[1, 0])
        assert s.score(item, [], GlobalWorkspace()) == 1.0

    def test_similar_to_workspace(self):
        s = NoveltySpecialist()
        ws = GlobalWorkspace(capacity=3)
        ws_item = _make_item(id="ws1", embedding=[1.0, 0.0, 0.0])
        ws.admit(ws_item)

        item = _make_item(id="cand", embedding=[1.0, 0.0, 0.0])
        score = s.score(item, [], ws)
        assert score < 0.1  # Very similar = low novelty


class TestCreateDefaults:
    def test_creates_six(self):
        specialists = create_default_specialists()
        assert len(specialists) == 6
        names = {s.name for s in specialists}
        assert names == {
            "relevance", "recency", "frequency",
            "structural_linkage", "goal_linkage", "novelty",
        }

    def test_weights_sum_to_one(self):
        specialists = create_default_specialists()
        total = sum(s.weight for s in specialists)
        assert abs(total - 1.0) < 1e-6
