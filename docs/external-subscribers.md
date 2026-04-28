# External Subscribers

`BroadcastBus` supports local deterministic subscribers and port-safe external
subscribers. External subscribers are the next architecture layer for LLM/NLI
processors without importing provider SDKs into `application`.

## Contract

Use `ExternalReasoningSubscriber` with an injected proposal function:

```python
from gwt_context.application.broadcast_bus import (
    BroadcastContext,
    BroadcastProposal,
    ExternalReasoningSubscriber,
)


def nli_proposals(context: BroadcastContext) -> tuple[BroadcastProposal, ...]:
    # Adapter-owned code can call an LLM/NLI service here.
    return (
        BroadcastProposal(
            subscriber="raw-provider-name",
            kind="flag_contradiction",
            priority=0.9,
            rationale="NLI model labelled the broadcast as contradiction.",
            payload={"label": "contradiction"},
        ),
    )


subscriber = ExternalReasoningSubscriber("nli_agent", nli_proposals)
```

The adapter sanitizes proposals:

- rewrites `subscriber` to the configured subscriber name,
- filters unsupported proposal kinds,
- filters below-threshold priorities,
- relies on `BroadcastBus` timeout/error reports for execution health.

## Allowed Proposal Kinds

- `query_memory`
- `resolve_answer`
- `flag_contradiction`
- `ask_followup`

These are the kinds `AttentionController` knows how to apply through public
ports or evidence-plan metadata.

## Boundary Rule

Provider-specific clients belong outside `src/gwt_context/application`, for
example in a future infrastructure adapter or deployment composition root. The
application layer receives only a callable and never imports OpenAI, vLLM,
transformers, or benchmark code.

## Release Gate

External subscribers must satisfy the same release thresholds:

- timeout count = 0,
- error count = 0,
- no bus-on accuracy regression,
- no tool-call regression beyond the documented threshold.
