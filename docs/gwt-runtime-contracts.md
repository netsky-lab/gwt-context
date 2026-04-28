# GWT Runtime Contracts

This document records the concrete runtime contract behind the GWT language in
the project.

## State Boundaries

| State | Owner | Allowed Inputs | Allowed Side Effects |
| --- | --- | --- | --- |
| Long-term memory | `IngestionPort` + `MemoryRepositoryPort` | `gwt_store`, persisted query results, linked records | Store and vector index writes through ingestion only. |
| Preconscious buffer | `SelectionBroadcastCycle` | stored items, admitted query matches, evicted workspace items, linked conscious targets | Rankable candidates only; items are not globally visible until competition admits them. |
| Conscious workspace | `GlobalWorkspace` through `SelectionBroadcastCycle` | competition winners above `GWT_MIN_ACTIVATION` | Broadcast formatting, broadcast history, state updates to `CONSCIOUS`. |
| Broadcast bus | `BroadcastBus` through `SelectionBroadcastCycle` | latest `BroadcastRecord` plus task context | Proposal reports only; subscribers do not mutate workspace or storage. |

## Admission Policy

- `CompetitionEngine` gates new workspace admissions with
  `GWT_MIN_ACTIVATION`. Below-threshold candidates remain preconscious.
- `AttentionController` applies bus proposals through `BusAdmissionPolicy`.
- `resolve_answer` proposals below `min_resolve_priority` are skipped.
- `query_memory` proposals below `min_query_priority` are skipped.
- Query proposals are suppressed after a deterministic answer is available
  unless the policy is configured otherwise.
- `flag_contradiction` and `ask_followup` are metadata side effects. They do
  not admit memory directly.

## Subscriber Execution

- Every subscriber receives the same `BroadcastContext`.
- Subscribers run through independent loop slots with a per-subscriber timeout.
- Each subscriber produces a `SubscriberReport` with `ok`, `timeout`, or
  `error` status.
- The bus arbitrates accepted proposals, records inhibited proposals, and
  penalizes repeated proposal keys over later broadcasts.
- Exact resolution inhibits lower-priority recall queries in the same broadcast
  arbitration round.

## Recurrent Link Activation

After each broadcast, conscious workspace items activate explicit `linked_ids`
into the preconscious buffer for the next cycle. This is the runtime reentry
path for graph-like memory: linked facts become eligible for the next
competition without parsing the rendered broadcast text.

## Benchmark Isolation

- Production `src/` modules must not import `tests.benchmarks`.
- Benchmark-specific controlled resolvers and generated task schemas live under
  `tests/benchmarks/`.
- `BENCHMARK_ATTEND_BROADCAST_BUS=0/1` isolates bus contribution for attend
  evaluations.
