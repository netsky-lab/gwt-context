"""Specialist processors for GWT competition.

Each specialist scores memory items from a different perspective.
Together they implement GWT marker #2 (functional concurrency) —
independent processors running in parallel.

Specialist protocol + 6 built-in implementations:
  - RelevanceSpecialist:       semantic similarity to active goal
  - RecencySpecialist:         temporal freshness (exponential decay)
  - FrequencySpecialist:       access frequency
  - StructuralLinkageSpecialist: pure connectivity to workspace items
  - GoalLinkageSpecialist:     connectivity weighted by goal-relevance of linked items
  - NoveltySpecialist:         dissimilarity to current workspace (anti-redundancy)
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from gwt_context.domain.models import Goal, MemoryItem
from gwt_context.domain.workspace import GlobalWorkspace

# Type alias for cosine similarity function: (vec_a, vec_b) -> float
SimilarityFn = Callable[[list[float], list[float]], float]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@runtime_checkable
class Specialist(Protocol):
    """Protocol for specialist processors that score memory items."""

    name: str
    weight: float

    def score(
        self,
        item: MemoryItem,
        goals: list[Goal],
        workspace: GlobalWorkspace,
    ) -> float:
        """Return activation score in [0, 1]."""
        ...


class RelevanceSpecialist:
    """Scores by semantic similarity to active goal embeddings.

    Weight: 0.35 — the strongest single signal.
    """

    name = "relevance"
    weight = 0.35

    def __init__(self, similarity_fn: SimilarityFn = cosine_similarity) -> None:
        self._sim = similarity_fn

    def score(
        self,
        item: MemoryItem,
        goals: list[Goal],
        workspace: GlobalWorkspace,
    ) -> float:
        if not goals or item.embedding is None:
            return 0.0
        max_sim = max(
            (
                self._sim(item.embedding, g.embedding) * g.priority
                for g in goals
                if g.embedding is not None
            ),
            default=0.0,
        )
        return max(min(max_sim, 1.0), 0.0)


class RecencySpecialist:
    """Scores by temporal recency with exponential decay.

    half_life_hours=2.0 means an item's recency score halves every 2 hours.
    """

    name = "recency"
    weight = 0.20

    def __init__(self, half_life_hours: float = 2.0) -> None:
        self._half_life = half_life_hours

    def score(
        self,
        item: MemoryItem,
        goals: list[Goal],
        workspace: GlobalWorkspace,
    ) -> float:
        now = datetime.now(UTC)
        age_hours = (now - item.last_accessed).total_seconds() / 3600
        if age_hours <= 0:
            return 1.0
        return math.exp(-0.693 * age_hours / self._half_life)


class FrequencySpecialist:
    """Scores by access frequency, capped at max_count."""

    name = "frequency"
    weight = 0.10

    def __init__(self, max_count: int = 20) -> None:
        self._max = max_count

    def score(
        self,
        item: MemoryItem,
        goals: list[Goal],
        workspace: GlobalWorkspace,
    ) -> float:
        return min(item.access_count / self._max, 1.0)


class StructuralLinkageSpecialist:
    """Scores by pure structural connectivity to workspace items.

    If item links to items in workspace, it scores higher regardless
    of current goal. This provides chain persistence — reasoning
    chains don't break on minor goal shifts.
    """

    name = "structural_linkage"
    weight = 0.10

    def score(
        self,
        item: MemoryItem,
        goals: list[Goal],
        workspace: GlobalWorkspace,
    ) -> float:
        if not item.linked_ids:
            return 0.0
        ws_ids = workspace.item_ids
        overlap = len(set(item.linked_ids) & ws_ids)
        return min(overlap / len(item.linked_ids), 1.0)


class GoalLinkageSpecialist:
    """Scores by connectivity weighted by goal-relevance of linked items.

    Unlike StructuralLinkageSpecialist, this weights each link by how
    relevant the linked item is to the current goal. Links to
    goal-irrelevant items contribute nothing.

    This is the key mechanism: multi-hop chains are boosted only when
    they lead TOWARD the goal, not just because they exist.
    """

    name = "goal_linkage"
    weight = 0.10

    def __init__(self, similarity_fn: SimilarityFn = cosine_similarity) -> None:
        self._sim = similarity_fn

    def score(
        self,
        item: MemoryItem,
        goals: list[Goal],
        workspace: GlobalWorkspace,
    ) -> float:
        if not item.linked_ids or not goals:
            return 0.0

        ws_items_by_id = {i.id: i for i in workspace.items}
        linked_in_ws = [
            ws_items_by_id[lid]
            for lid in item.linked_ids
            if lid in ws_items_by_id
        ]
        if not linked_in_ws:
            return 0.0

        # Weight each link by the linked item's relevance to goal
        total_relevance = 0.0
        for linked_item in linked_in_ws:
            if linked_item.embedding is None:
                continue
            best_goal_sim = max(
                (
                    self._sim(linked_item.embedding, g.embedding)
                    for g in goals
                    if g.embedding is not None
                ),
                default=0.0,
            )
            total_relevance += max(best_goal_sim, 0.0)

        avg_relevance = total_relevance / len(linked_in_ws)
        return min(avg_relevance, 1.0)


class NoveltySpecialist:
    """Scores by dissimilarity to current workspace contents.

    Prevents redundancy: items that are very similar to what's already
    in workspace get penalised, ensuring information diversity.
    """

    name = "novelty"
    weight = 0.15

    def __init__(self, similarity_fn: SimilarityFn = cosine_similarity) -> None:
        self._sim = similarity_fn

    def score(
        self,
        item: MemoryItem,
        goals: list[Goal],
        workspace: GlobalWorkspace,
    ) -> float:
        ws_items = workspace.items
        if not ws_items or item.embedding is None:
            return 1.0  # Novel by default when workspace empty
        similarities = [
            self._sim(item.embedding, wi.embedding)
            for wi in ws_items
            if wi.embedding is not None
        ]
        if not similarities:
            return 1.0
        avg_sim = sum(similarities) / len(similarities)
        return max(1.0 - avg_sim, 0.0)


def create_default_specialists(
    similarity_fn: SimilarityFn = cosine_similarity,
) -> list[Specialist]:
    """Create the standard set of 6 specialists.

    Weights sum to 1.0:
      relevance=0.35, recency=0.20, frequency=0.10,
      structural_linkage=0.10, goal_linkage=0.10, novelty=0.15
    """
    return [
        RelevanceSpecialist(similarity_fn),
        RecencySpecialist(),
        FrequencySpecialist(),
        StructuralLinkageSpecialist(),
        GoalLinkageSpecialist(similarity_fn),
        NoveltySpecialist(similarity_fn),
    ]
