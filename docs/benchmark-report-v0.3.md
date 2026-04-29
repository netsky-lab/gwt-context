# v0.3 Benchmark Report

Status as of 2026-04-29: bounded Qwen/OpenAI-compatible sanity for
`v0.3.0-rc1`.

This report summarizes the latest ignored benchmark artifacts under
`.benchmarks/qwen-sanity/`. Raw JSON results are intentionally not committed.

## Matrix

Command:

```bash
npm run qwen:sanity -- --run --max-tasks 5
```

The wrapper executes bounded bus-on and bus-off slices for RULER multi-hop and
LongBench Pro synthetic tasks using deterministic local GWT embeddings.

| Benchmark | Mode | Tasks | GWT acc | Baseline acc | Evidence recall | Evidence precision | Bus accepted / inhibited |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RULER advisor | attend / bus on | 2 | 100.0% | 100.0% | 100.0% | 31.0% | 2 / 4 |
| RULER advisor | attend / bus off | 2 | 100.0% | 100.0% | 100.0% | 31.0% | 0 / 0 |
| LongBench count/filter/aggregate/top_k/synthesis | attend / bus on | 5 | 100.0% | 100.0% | 100.0% | 32.1% | 5 / 5 |
| LongBench count/filter/aggregate/top_k/synthesis | attend / bus off | 5 | 100.0% | 80.0% | 100.0% | 35.7% | 0 / 0 |

## Release Gates

| Gate | Status | Actual | Threshold |
| --- | --- | ---: | ---: |
| RULER | pass | 100.0% | 90.0% |
| count | pass | 100.0% | 90.0% |
| filter | pass | 100.0% | 90.0% |
| aggregate | pass | 100.0% | 90.0% |
| synthesis | pass | 100.0% | 80.0% |
| top_k | pass | 100.0% | 80.0% |

The local test baseline for this RC polish is `206 passed`.

## Bus Deltas

| Benchmark | Tasks | Accuracy delta | Tool-call delta | Accepted delta |
| --- | ---: | ---: | ---: | ---: |
| RULER advisor | 2 | +0.0% | +0.00 | +2 |
| LongBench Pro | 5 | +0.0% | +0.00 | +5 |

Bus inhibition reasons were present in the summary:

- RULER: `resolved_answer_present=4`
- LongBench Pro: `resolved_answer_present=5`

Subscriber timeout/error counts were `0 / 0` in every slice.

## Notable Delta

In the bus-off LongBench slice, baseline missed one synthesis task:

- Task: `lbp_synthesis_12rec_0`
- Expected: `Design`
- GWT: `Design`
- Baseline: `Neither, they have the same average years of experience (16 years).`

This is a useful sanity signal, not a broad benchmark claim. The sample is still
small and should be expanded before final `v0.3.0`.

## Artifact References

Latest ignored local artifacts used for this report:

- `.benchmarks/qwen-sanity/ruler_multi_hop_qwen3.6-35b-a3b_20260429_120705_106121_64bcba02f39d.json`
- `.benchmarks/qwen-sanity/ruler_multi_hop_qwen3.6-35b-a3b_20260429_120729_308788_6c4c4f47b26c.json`
- `.benchmarks/qwen-sanity/longbench_pro_qwen3.6-35b-a3b_20260429_120712_407378_64bcba02f39d.json`
- `.benchmarks/qwen-sanity/longbench_pro_qwen3.6-35b-a3b_20260429_120734_749989_6c4c4f47b26c.json`
