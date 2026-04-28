"""Tests for infrastructure-owned external subscriber adapters."""

from collections.abc import Mapping, Sequence

from gwt_context.application.broadcast_bus import BroadcastContext
from gwt_context.infrastructure.external_subscribers import JsonProposalAdapter


class FakeClient:
    def complete(self, messages: Sequence[Mapping[str, str]]) -> str:
        assert messages[0]["role"] == "system"
        assert "Broadcast:" in messages[1]["content"]
        return """
        {
          "proposals": [
            {
              "kind": "flag_contradiction",
              "priority": 1.7,
              "rationale": "conflict found",
              "payload": {"label": "contradiction"}
            },
            {
              "kind": "",
              "priority": 0.9,
              "rationale": "ignored",
              "payload": {}
            }
          ]
        }
        """


def test_json_proposal_adapter_parses_and_clamps_proposals() -> None:
    adapter = JsonProposalAdapter(FakeClient())

    proposals = adapter(
        BroadcastContext(
            question="Is this conflicting?",
            broadcast_id="b1",
            broadcast_text="Ada score=9\nAda score=6",
            pass_number=1,
            evidence_plan=None,
            context_chunks=("Ada score=9", "Ada score=6"),
        )
    )

    assert len(proposals) == 1
    assert proposals[0].kind == "flag_contradiction"
    assert proposals[0].priority == 1.0
    assert proposals[0].payload["label"] == "contradiction"
