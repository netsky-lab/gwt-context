# Dogfood Report

Status as of 2026-04-29: local MCP usage, Codex namespace health, external
subscriber wiring, and bounded Qwen sanity all pass.

## Local MCP Usage Loop

Command:

```bash
python examples/real_usage_loop.py
```

Observed on 2026-04-29:

| Signal | Value |
| --- | --- |
| Graph answer | `Paper Gamma` |
| Collection answer | `Ada` |
| Bus accepted / inhibited | `1 / 2` |
| Subscriber statuses | `ok, ok, ok, ok, ok` |
| Trace status | `ok` |
| Workspace size | `4` |

This proves the public in-process MCP handlers can store records, resolve a
graph path, run a collection query, expose bus activity, explain the trace, and
inspect workspace state without external embedding downloads.

## External Subscriber POC

Command:

```bash
python examples/external_subscriber_poc.py
```

Observed on 2026-04-29:

| Signal | Value |
| --- | --- |
| Accepted proposal kinds | `flag_contradiction`, `query_memory` |
| Accepted proposals | `2` |
| Inhibited proposals | `0` |
| Subscriber statuses | `ok: 2` |
| Timeout / error | `0 / 0` |

This proves provider-edge subscribers can be adapted into bus proposals without
importing provider SDKs into `application`.

## Codex MCP Health

Command:

```bash
npm run memory:health -- --smoke --json
```

Observed on 2026-04-29:

| Signal | Value |
| --- | --- |
| Project namespace | exists, `memory.db=true` |
| Global namespace | exists, `memory.db=true` |
| Temp stdio MCP smoke | `returncode=0` |
| MCP tool count | `21` |
| Smoke answer | `Paper Gamma` |
| Smoke bus accepted / inhibited | `1 / 2` |
| Smoke trace status | `ok` |

Namespace vector files may be absent until a namespace has persisted vectors for
that local configuration. The smoke runs against a temporary namespace with
hash embeddings.

## Bounded Qwen Sanity

Command:

```bash
npm run qwen:sanity -- --run --max-tasks 5
```

Observed on 2026-04-29 against the configured OpenAI-compatible Qwen endpoint:

| Benchmark | Mode | Tasks | GWT | Baseline | Avg calls | Bus accepted / inhibited | Timeout / error |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RULER advisor | bus on | 2 | 100% | 100% | 3.0 | `2 / 4` | `0 / 0` |
| RULER advisor | bus off | 2 | 100% | 100% | 3.0 | `0 / 0` | `0 / 0` |
| LongBench count/filter/aggregate/top_k/synthesis | bus on | 5 | 100% | 100% | 3.0 | `5 / 5` | `0 / 0` |
| LongBench count/filter/aggregate/top_k/synthesis | bus off | 5 | 100% | 80% | 3.0 | `0 / 0` | `0 / 0` |

Bus inhibition reasons in this bounded run were `resolved_answer_present=4` for
RULER and `resolved_answer_present=5` for LongBench. The detailed table is in
`docs/benchmark-report-v0.3.md`.

## Interpretation

This is enough for a release candidate and real local use. It is not enough to
claim broad benchmark superiority. The next evidence step is a larger matrix
with more seeds, more distractors, larger LongBench record counts, and
multi-pass variants.
