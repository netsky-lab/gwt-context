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

For OpenAI-compatible endpoints, infrastructure code can build the proposal
callable without importing provider clients into `application`:

```python
from gwt_context.infrastructure.external_subscribers import (
    OpenAICompatibleSubscriberConfig,
    build_openai_compatible_subscriber,
)


subscriber = build_openai_compatible_subscriber(
    "nli_agent",
    OpenAICompatibleSubscriberConfig(
        api_base="https://example-openai-compatible-endpoint/v1",
        model="qwen3.6-35b-a3b",
        api_key="test",
    ),
)
```

The adapter sanitizes proposals:

- rewrites `subscriber` to the configured subscriber name,
- filters unsupported proposal kinds,
- filters below-threshold priorities,
- relies on `BroadcastBus` timeout/error reports for execution health.

## Runtime Wiring

The default MCP server can attach one OpenAI-compatible external subscriber from
environment variables. It is disabled by default.

```bash
GWT_EXTERNAL_SUBSCRIBER_ENABLED=true
GWT_EXTERNAL_SUBSCRIBER_NAME=external_reasoner
GWT_EXTERNAL_SUBSCRIBER_API_BASE=https://example-openai-compatible-endpoint/v1
GWT_EXTERNAL_SUBSCRIBER_MODEL=qwen3.6-35b-a3b
GWT_EXTERNAL_SUBSCRIBER_API_KEY=test
GWT_EXTERNAL_SUBSCRIBER_TIMEOUT_SECONDS=10
GWT_EXTERNAL_SUBSCRIBER_MIN_PRIORITY=0.5
```

Bus-level budgets are separate from provider HTTP timeout:

```bash
GWT_BROADCAST_BUS_MAX_ACCEPTED=4
GWT_BROADCAST_BUS_THRESHOLD=0.5
GWT_BROADCAST_BUS_TIMEOUT_SECONDS=0.25
GWT_BROADCAST_BUS_MAX_PROPOSALS_PER_SUBSCRIBER=4
GWT_BROADCAST_BUS_MAX_PAYLOAD_CHARS=4000
GWT_BROADCAST_BUS_CIRCUIT_BREAKER_FAILURES=3
```

`GWT_BROADCAST_BUS_TIMEOUT_SECONDS` is intentionally small because the bus runs
inside the normal broadcast path. Slow external agents should be tested with a
larger local budget before being used in day-to-day MCP sessions.
After repeated timeout/error reports, the circuit breaker reports
`circuit_open` for that subscriber until the MCP process restarts.

Run the deterministic proof-of-concept:

```bash
python examples/external_subscriber_poc.py
```

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
