"""Competition engine — the core GWT selection mechanism.

Implements GWT markers:
  #3 Coordinated selection — single arbitration step with unified scoring
  #6 Goal-modulated arbitration — goal relevance provides multiplicative boost

Scoring formula:
  activation(item) = Σ(specialist.weight × specialist.score(item)) / Σ(weights)
  final(item) = activation × (1.0 + goal_modulation_strength × relevance(item))
"""

from __future__ import annotations

from gwt_context.domain.models import CompetitionResult, Goal, MemoryItem
from gwt_context.domain.specialists import Specialist
from gwt_context.domain.workspace import GlobalWorkspace


class CompetitionEngine:
    """Runs competition rounds where memory items compete for workspace slots.

    All specialists score every candidate. Scores are combined via weighted
    average, then goal-modulated. Top-scoring items win workspace slots,
    potentially evicting weaker current occupants.
    """

    def __init__(
        self,
        specialists: list[Specialist],
        goal_modulation_strength: float = 0.3,
        min_activation: float = 0.2,
    ) -> None:
        self._specialists = specialists
        self._goal_mod = goal_modulation_strength
        self._min_activation = min_activation

    @property
    def specialists(self) -> list[Specialist]:
        return list(self._specialists)

    def score_item(
        self,
        item: MemoryItem,
        goals: list[Goal],
        workspace: GlobalWorkspace,
    ) -> float:
        """Compute final activation score for a single item."""
        total_weight = sum(s.weight for s in self._specialists)
        if total_weight == 0:
            return 0.0

        raw = sum(
            s.weight * s.score(item, goals, workspace)
            for s in self._specialists
        ) / total_weight

        # Goal modulation (GWT marker #6)
        goal_alignment = self._get_relevance_score(item, goals, workspace)
        final = raw * (1.0 + self._goal_mod * goal_alignment)
        return min(final, 1.0)

    def run_competition(
        self,
        candidates: list[MemoryItem],
        goals: list[Goal],
        workspace: GlobalWorkspace,
        n_winners: int | None = None,
    ) -> CompetitionResult:
        """Run one competition round.

        Args:
            candidates: Items competing for workspace entry.
            goals: Active goals for modulation.
            workspace: Current workspace state.
            n_winners: Max items to admit. Defaults to free slots.

        Returns:
            CompetitionResult with winners, evicted, and all scores.
        """
        if n_winners is None:
            n_winners = workspace.capacity

        # Score all candidates (excluding those already in workspace)
        scores: dict[str, float] = {}
        ws_ids = workspace.item_ids
        external_candidates = [c for c in candidates if c.id not in ws_ids]

        for item in external_candidates:
            score = self.score_item(item, goals, workspace)
            scores[item.id] = score
            item.activation_level = score

        # Score current workspace occupants for comparison
        ws_scores: dict[str, float] = {}
        for ws_item in workspace.items:
            score = self.score_item(ws_item, goals, workspace)
            ws_scores[ws_item.id] = score
            ws_item.activation_level = score

        # Ignition threshold gates admission. Weak candidates stay
        # preconscious instead of filling empty slots by default.
        eligible_external = [
            item for item in external_candidates
            if scores.get(item.id, 0.0) >= self._min_activation
        ]

        # Merge current workspace with eligible external items and keep top-N
        # (N = workspace capacity). Existing workspace items are not evicted
        # solely because they fall below the ignition threshold.
        all_items = workspace.items + eligible_external
        all_scores = {**ws_scores, **scores}
        all_sorted = sorted(
            all_items,
            key=lambda i: all_scores.get(i.id, 0.0),
            reverse=True,
        )

        keepers = all_sorted[:n_winners]
        keeper_ids = {k.id for k in keepers}

        # Determine evictions and admissions
        evicted = [i for i in workspace.items if i.id not in keeper_ids]
        winners = [i for i in keepers if i.id not in ws_ids]
        winner_ids = {item.id for item in winners}
        evicted_ids = {item.id for item in evicted}
        reason_breakdown: dict[str, str] = {}
        for item in external_candidates:
            score = scores.get(item.id, 0.0)
            if item.id in winner_ids:
                reason_breakdown[item.id] = "admitted"
            elif score < self._min_activation:
                reason_breakdown[item.id] = "below_ignition_threshold"
            else:
                reason_breakdown[item.id] = "eligible_not_selected"
        for item in workspace.items:
            if item.id in evicted_ids:
                reason_breakdown[item.id] = "evicted_by_higher_activation"
            else:
                reason_breakdown[item.id] = "kept_in_workspace"

        # Merge scores for the result
        all_scores.update(scores)

        return CompetitionResult(
            winners=winners,
            evicted=evicted,
            scores=all_scores,
            reason="ignition_threshold" if external_candidates and not eligible_external else "",
            reason_breakdown=reason_breakdown,
        )

    def _get_relevance_score(
        self,
        item: MemoryItem,
        goals: list[Goal],
        workspace: GlobalWorkspace,
    ) -> float:
        """Extract the relevance specialist's raw score for goal modulation."""
        for s in self._specialists:
            if s.name == "relevance":
                return s.score(item, goals, workspace)
        return 0.0
