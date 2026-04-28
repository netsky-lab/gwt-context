"""Proof-of-concept external subscriber wiring for the broadcast bus."""

from __future__ import annotations

import json

from gwt_context.application.broadcast_bus import (
    BroadcastBus,
    BroadcastContext,
    ExternalReasoningSubscriber,
    StructuredResolverSubscriber,
    broadcast_bus_result_to_dict,
)
from gwt_context.infrastructure.external_subscribers import JsonProposalAdapter


class FakeChatClient:
    """Deterministic stand-in for an OpenAI-compatible subscriber transport."""

    def complete(self, messages):  # type: ignore[no-untyped-def]
        """Return proposal JSON as if an external agent produced it."""
        return """
        {
          "proposals": [
            {
              "kind": "flag_contradiction",
              "priority": 0.88,
              "rationale": "External checker saw conflicting score evidence.",
              "payload": {
                "label": "possible_conflict",
                "question": "Is there any conflicting evidence?"
              }
            },
            {
              "kind": "query_memory",
              "priority": 0.62,
              "rationale": "External planner wants to continue the citation chain.",
              "payload": {"query": "Paper Beta cites"}
            }
          ]
        }
        """


def run_poc() -> dict[str, object]:
    """Run the external subscriber through normal bus arbitration."""
    bus = BroadcastBus(
        subscribers=[
            StructuredResolverSubscriber(),
            ExternalReasoningSubscriber(
                "external_nli_agent",
                JsonProposalAdapter(FakeChatClient()),
                min_priority=0.5,
            ),
        ],
        max_accepted=3,
    )
    result = bus.publish(
        BroadcastContext(
            question="Is there any conflicting evidence and what should we recall next?",
            broadcast_id="demo-broadcast",
            broadcast_text=(
                "Paper Alpha -> cites -> Paper Beta\n"
                "emp-001 | name=Ada | team=research | score=9\n"
                "emp-001 | name=Ada | team=research | score=6"
            ),
            pass_number=1,
            evidence_plan=None,
            context_chunks=(
                "emp-001 | name=Ada | team=research | score=9",
                "emp-001 | name=Ada | team=research | score=6",
            ),
        )
    )
    return broadcast_bus_result_to_dict(result)


def main() -> None:
    """Print the bus result for the external subscriber proof-of-concept."""
    print(json.dumps(run_poc(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
