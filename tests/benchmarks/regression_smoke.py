"""Deterministic benchmark smoke for controlled attention paths.

This smoke avoids external model calls and embedding downloads. It checks that
generated benchmark tasks still resolve evidence and execute the application
attention loop shape used by controlled/hybrid modes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from gwt_context.application.attention import AttentionController
from gwt_context.domain.models import Goal, MemoryItem
from tests.benchmarks.controlled_rules import build_benchmark_resolvers
from tests.benchmarks.longbench_pro import generate_tasks as generate_longbench_tasks
from tests.benchmarks.ruler_multi_hop import generate_tasks as generate_ruler_tasks


@dataclass
class SmokeCycle:
    """Small port-shaped cycle double for benchmark smoke."""

    admitted: list[MemoryItem] = field(default_factory=list)
    goal: Goal | None = None

    def set_goal(
        self,
        description: str,
        keywords: list[str] | None = None,
        priority: float = 1.0,
    ) -> Goal:
        self.goal = Goal(description=description, keywords=keywords or [], priority=priority)
        return self.goal

    def enqueue_for_competition(self, item: MemoryItem) -> None:
        self.admitted.append(item)

    def run(self, **_kwargs: Any) -> Any:
        content = "\n".join(item.content for item in self.admitted[:7])
        return type(
            "SmokeRecord",
            (),
            {
                "id": "smoke-broadcast",
                "formatted_content": content,
                "admitted_ids": [item.id for item in self.admitted[:7]],
                "evicted_ids": [],
            },
        )()

    def get_last_broadcast_bus_result(self) -> None:
        return None


class SmokeIngestion:
    """Port-shaped semantic search double backed by task chunks."""

    def __init__(self, chunks: list[str]) -> None:
        self._items = [
            MemoryItem(id=f"item-{index}", content=chunk)
            for index, chunk in enumerate(chunks)
        ]

    def query_similar(
        self,
        query: str,
        k: int = 10,
        memory_type: object | None = None,
    ) -> list[MemoryItem]:
        del memory_type
        query_terms = {term.lower().strip(" ?'\".,") for term in query.split() if len(term) > 2}
        ranked = sorted(
            self._items,
            key=lambda item: _overlap(query_terms, item.content),
            reverse=True,
        )
        return ranked[:k]


def run_smoke() -> dict[str, Any]:
    """Run deterministic benchmark smoke and return a compact report."""
    tasks = [
        generate_ruler_tasks(n_hops_list=[2], distractor_counts=[3], tasks_per_config=1)[0],
        generate_longbench_tasks(
            task_types=["synthesis"],
            record_counts=[12],
            tasks_per_config=1,
        )[0],
    ]
    results = []
    for task in tasks:
        cycle = SmokeCycle()
        ingestion = SmokeIngestion(task.context_chunks)
        controller = AttentionController(
            cycle=cycle,
            ingestion=ingestion,
            resolvers=build_benchmark_resolvers(),
            query_k=5,
        )
        run = controller.run(task.question, task.context_chunks, task.metadata)
        correct = task.expected_answer.lower() in run.evidence.answer.lower()
        results.append(
            {
                "task_id": task.id,
                "strategy": run.evidence.strategy,
                "expected": task.expected_answer,
                "predicted": run.evidence.answer,
                "correct": correct,
                "tool_call_count": run.tool_call_count,
                "admitted_count": len(run.admitted_ids),
            }
        )

    return {
        "task_count": len(results),
        "correct": sum(1 for result in results if result["correct"]),
        "results": results,
    }


def _overlap(query_terms: set[str], content: str) -> int:
    content_terms = {term.lower().strip(" ?'\".,") for term in content.split()}
    return len(query_terms & content_terms)


def main() -> None:
    report = run_smoke()
    print(json.dumps(report, indent=2))
    if report["correct"] != report["task_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
