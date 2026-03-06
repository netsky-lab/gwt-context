"""Goal management — tracks active objectives for competition modulation."""

from __future__ import annotations

from gwt_context.domain.models import Goal
from gwt_context.infrastructure.embeddings import EmbeddingProvider
from gwt_context.infrastructure.storage import SQLiteMemoryStore


class GoalManager:
    """Manages goals that modulate the GWT competition.

    Supports multiple active goals with priorities. When a new goal
    is set, previous goals are deactivated by default (single-goal mode)
    or kept active (multi-goal mode).
    """

    def __init__(
        self,
        store: SQLiteMemoryStore,
        embedder: EmbeddingProvider,
    ) -> None:
        self._store = store
        self._embedder = embedder

    @property
    def active_goals(self) -> list[Goal]:
        return self._store.get_active_goals()

    def set_goal(
        self,
        description: str,
        keywords: list[str] | None = None,
        priority: float = 1.0,
        replace: bool = True,
    ) -> Goal:
        """Set a new active goal.

        Args:
            description: Natural language objective.
            keywords: Optional keywords for boosting.
            priority: Influence strength (0.1 to 2.0).
            replace: If True, deactivate all previous goals first.
        """
        if replace:
            self._store.deactivate_all_goals()

        goal = Goal(
            description=description,
            keywords=keywords or [],
            priority=max(0.1, min(priority, 2.0)),
        )
        goal.embedding = self._embedder.embed(description)
        self._store.save_goal(goal)
        return goal

    def deactivate_all(self) -> None:
        self._store.deactivate_all_goals()
