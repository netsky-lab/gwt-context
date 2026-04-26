# GWT Design Rationale

This note maps the current `gwt-context` design to the 2025-2026 research cache
in this folder. It is a design rationale, not a consciousness claim.

## Core Claim

Large context windows solve storage pressure, not working-memory arbitration.
The architectural problem this project targets is selection: which few memories
become globally available to the model for the next reasoning step.

## Why Selection-Broadcast Is Explicit

Nakanishi et al. frame the selection-broadcast cycle as a functional structure
for real-time systems rather than a loose metaphor. For this repo, that supports
keeping candidate gathering, competition, workspace admission/eviction, and
broadcast as separate observable steps.

Design consequences:

- `SelectionBroadcastCycle.run()` is the central orchestration point.
- `gwt_broadcast` is not a formatting helper; it is the visible cycle trigger.
- Benchmark traces should record candidates, scores, admitted items, evictions,
  and workspace state.

Primary source:

- [`papers/2025-nakanishi-selection-broadcast-cycle.pdf`](papers/2025-nakanishi-selection-broadcast-cycle.pdf)

## Why The Workspace Is Bounded

GWT/GNWT-inspired systems are useful here because they make capacity limits a
first-class part of cognition. A bounded workspace forces competition and makes
eviction observable when the task goal changes.

Design consequences:

- `GlobalWorkspace` has explicit capacity.
- Competition winners are admitted; weaker or displaced items leave active
  context.
- Benchmark reports must track cases where GWT helps or hurts under capacity
  pressure, not only whether retrieval found an item.

Related sources:

- [`papers/2026-shang-theater-of-mind-gwa.pdf`](papers/2026-shang-theater-of-mind-gwa.pdf)
- [`papers/2025-ye-cognipair-gnwt-agents.pdf`](papers/2025-ye-cognipair-gnwt-agents.pdf)

## Why Goals Modulate Selection

The workspace should not be a generic top-k semantic search result. Current
task goals should bias competition, and goal changes should be able to reshape
the workspace.

Design consequences:

- `GoalManager` computes goal embeddings and exposes active goals through a
  port.
- Competition applies goal modulation to candidate scores.
- Tool policy should make `gwt_set_goal` an early action, not an optional
  afterthought.

Related sources:

- [`papers/2025-hu-unified-mind-model.pdf`](papers/2025-hu-unified-mind-model.pdf)
- [`papers/2025-ye-cognipair-gnwt-agents.pdf`](papers/2025-ye-cognipair-gnwt-agents.pdf)

## Why Routing And Multi-Hop Links Matter

Chateau-Laurent and VanRullen show the relevance of routing information through
a global workspace for chained operations. In this project, bidirectional memory
links and structural/goal linkage scoring are the pragmatic counterpart.

Design consequences:

- `gwt_link` is part of the external API, not an internal storage detail.
- Link-aware specialists should be measured on multi-hop benchmarks such as
  RULER-style sequential NIAH tasks.
- Benchmark traces should include query results and workspace snapshots so we
  can see whether chain facts actually entered active context.

Primary source:

- [`papers/2025-chateau-laurent-routing-through-global-workspace.pdf`](papers/2025-chateau-laurent-routing-through-global-workspace.pdf)

## Why The MCP Boundary Uses Read Models

The MCP layer should expose the workspace and resources without reaching into
runtime internals. GWT is most useful as an architecture when the boundaries are
observable and testable; direct internal access makes the boundary unmeasurable.

Design consequences:

- MCP tools delegate to `CyclePort`/`IngestionPort`.
- MCP resources consume `cycle.inspect(...)` read models and
  `get_workspace_broadcast()`.
- `server.py` remains the composition root that wires infrastructure.

Related sources:

- [`papers/2026-shang-theater-of-mind-gwa.pdf`](papers/2026-shang-theater-of-mind-gwa.pdf)

## What We Should Not Claim

This project does not claim phenomenal consciousness, sentience, or subjective
experience. The research supports architectural mechanisms:

- global availability,
- specialist competition,
- bounded active workspace,
- goal-modulated selection,
- broadcast into active context.

Those mechanisms can be useful for agent memory even if they remain purely
functional engineering constructs.

## Current Evaluation Gaps

The Tait/Rode/Bensemann marker paper is tracked as link-only in
[`README.md`](README.md) because direct PDF download returned HTTP 403 during
cache creation. It is still important because it argues for marker-level
evaluation of global workspace behavior.

Immediate evaluation implications:

- Store raw model answers.
- Store tool traces.
- Store workspace snapshots.
- Store competition scores and evictions.
- Report failure buckets, not only accuracy.

Link-only source:

- <https://www.preprints.org/manuscript/202601.1683/v1>
