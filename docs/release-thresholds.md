# Release Thresholds

These gates decide whether a bus-affecting change can be tagged as a release.

## Blocking Gates

| Gate | Threshold |
| --- | --- |
| Unit/integration tests | `pytest -q` passes |
| Static checks | `ruff check .` and `mypy src` pass |
| npm verification | `npm test -- --quiet` passes |
| Smoke | `python -m gwt_context.smoke` passes with hash embeddings |
| Build | `python -m build` succeeds |
| Boundary checks | MCP/application grep checks return no hits |
| Secret/artifact checks | no tracked benchmark results, `.env`, `dist/`, RunPod URLs |
| Family accuracy | RULER/count/filter/aggregate >= 90%; synthesis/top_k >= 80% |
| Bus accuracy regression | bus-on GWT accuracy must be >= bus-off for the same slice |
| Bus tool-call regression | bus-on average tool calls <= bus-off + 0.25 |
| Bus subscriber health | timeout count = 0 and error count = 0 |
| Bus arbitration audit | benchmark summary includes inhibited reason counts |

## Tracked Non-Blocking Metrics

- Evidence precision/recall by family.
- Bus accepted/inhibited proposal counts.
- Bus inhibition reason counts (`below_threshold`, `duplicate_key`,
  `max_accepted`, `resolved_answer_present`).
- Bus tool actions.
- Baseline accuracy and latency.
- GWT workspace occupancy.

## Current Release Matrix

Latest Qwen matrix on 2026-04-28:

| Slice | Bus | Tasks | GWT | Baseline | Avg Calls | Bus accepted/inhibited | Timeout/error |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RULER advisor/workplace/discovery | on | 12 | 100% | 100% | 3.0 | 12 / 24 | 0 / 0 |
| RULER advisor/workplace/discovery | off | 12 | 100% | 100% | 3.0 | 0 / 0 | 0 / 0 |
| LongBench count/filter/aggregate/top_k/synthesis | on | 10 | 100% | 100% | 3.0 | 10 / 10 | 0 / 0 |
| LongBench count/filter/aggregate/top_k/synthesis | off | 10 | 100% | 100% | 3.0 | 0 / 0 | 0 / 0 |

All blocking release gates passed for `v0.2.0`. `v0.3.0` now has a bounded RC
sanity run after the memory-management and external-subscriber runtime changes;
the final tag still needs the larger release matrix refreshed.

## Current v0.3.0 RC Sanity

Latest bounded Qwen sanity on 2026-04-28 after memory management, bus budgets,
competition reasons, and structured parser expansion:

| Slice | Bus | Tasks | GWT | Baseline | Avg Calls | Bus accepted/inhibited | Timeout/error |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RULER advisor | on | 2 | 100.0% | 100.0% | 3.0 | 2 / 4 | 0 / 0 |
| RULER advisor | off | 2 | 100.0% | 100.0% | 3.0 | 0 / 0 | 0 / 0 |
| LongBench count/filter | on | 2 | 100.0% | 100.0% | 3.0 | 2 / 2 | 0 / 0 |
| LongBench count/filter | off | 2 | 100.0% | 100.0% | 3.0 | 0 / 0 | 0 / 0 |

Bus inhibition reasons were present in the summary:
`resolved_answer_present=4` for RULER and `resolved_answer_present=2` for
LongBench. This satisfies the bounded RC sanity gate; it does not replace the
larger release matrix for a final tag.
