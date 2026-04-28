# Honest GWT Report

Status as of 2026-04-28: `gwt-context` is a practical GWT-inspired MCP memory
runtime. It has more than retrieval plus a prompt template, but it is still not
a full cognitive Global Workspace model.

## What Is Real

- There is a bounded conscious workspace. Candidates must compete before they
  become globally visible.
- Workspace admission has ignition gating through `GWT_MIN_ACTIVATION`; weak
  candidates are not admitted only because a slot is empty.
- Broadcast is now an event, not only a rendered text response. After each
  broadcast, `SelectionBroadcastCycle` publishes the same content to a
  `BroadcastBus`.
- Independent subscribers read the broadcast and propose actions. Current local
  subscribers cover structured resolution, semantic recall, relation
  continuation, contradiction flags, and follow-up critique.
- Accepted proposals can affect runtime behavior. `resolve_answer` updates the
  deterministic evidence plan, `query_memory` admits new candidates through
  public ports, and conflict/follow-up proposals are recorded as trace metadata.
- The bus records proposals, accepted actions, inhibited repeats, subscriber
  reports, timeout/error status, and arbitration reason codes.
- Conscious records can reactivate explicit `linked_ids` back into the
  preconscious buffer on the next cycle, which gives the runtime a concrete
  reentry path that does not parse broadcast text.
- External agent loops have a port-safe adapter path through
  `ExternalReasoningSubscriber`; provider SDKs stay outside `application`.

## What Is Still GWT-Inspired, Not Full GWT

- Most built-in subscribers are deterministic local processors, not separate
  long-running agent processes with their own memory and tool loops.
- Arbitration is explicit and inspectable, but it is not learned. Priority,
  thresholds, deduplication, and policy rules are engineered.
- The runtime has short recurrent cycles, not open-ended cognitive dynamics.
  Multi-pass attention is opt-in through `gwt_attend(passes=...)`.
- Broadcast makes content available to processors inside this runtime. It does
  not make content globally available to every subsystem in a larger host agent
  unless that host wires those subsystems as subscribers.
- Current benchmark gains mostly prove controlled exact selection, bus health,
  and no regression. They do not prove universal long-context reasoning gains.

## Best Current Claim

The honest claim is:

> `gwt-context` implements a bounded working-memory runtime where facts compete
> for global availability, broadcasts are consumed by independent proposal
> processors, and accepted proposals can drive the next memory actions through
> public MCP/application ports.

The weaker claim to avoid is:

> This is a complete Global Workspace Theory implementation for LLM agents.

## Design Implication

The next architectural frontier is processor independence. The runtime already
has the bus boundary, proposal contracts, circuit breakers, budgets, traces, and
external subscriber adapter. To become more GWT-like, more reasoning must move
out of a single controller call and into independent subscriber loops that read
the same broadcast, maintain their own local state, and compete through the bus.

