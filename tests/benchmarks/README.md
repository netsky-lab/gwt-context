# Benchmark harness

## Setup

Install benchmark dependencies and dependencies used by benchmarks:

```bash
pip install -e ".[dev,bench]"
```

Copy defaults and edit if needed:

```bash
cp .env.example .env
```

## Required benchmark env

- `BENCHMARK_API_BASE` (required) - API host (for example `https://...runpod...`)
- `BENCHMARK_MODEL` (required) - model name accepted by the endpoint
- `BENCHMARK_API_KEY` (required if your provider validates auth)

## Optional benchmark env

- `BENCHMARK_API_PATH` (default `/v1`) - relative path appended to base URL
- `BENCHMARK_TIMEOUT_SECONDS` (default `30`) - request timeout seconds
- `BENCHMARK_API_HEADERS` - JSON or CSV `key=value` headers
- `BENCHMARK_MAX_RETRIES` (default `2`)
- `BENCHMARK_CONCURRENCY` (default `1`) - number of independent benchmark tasks to run in parallel
- `BENCHMARK_RESULTS_DIR` (default `tests/benchmarks/results`)

## Run commands

```bash
python -m tests.benchmarks.ruler_multi_hop \
  --api-base "$BENCHMARK_API_BASE" \
  --api-path "$BENCHMARK_API_PATH" \
  --model "$BENCHMARK_MODEL" \
  --api-key "$BENCHMARK_API_KEY" \
  --gwt-mode controlled \
  --max-tasks 3

python -m tests.benchmarks.longbench_pro \
  --api-base "$BENCHMARK_API_BASE" \
  --api-path "$BENCHMARK_API_PATH" \
  --model "$BENCHMARK_MODEL" \
  --api-key "$BENCHMARK_API_KEY" \
  --gwt-mode controlled \
  --timeout 60 \
  --results-dir tests/benchmarks/results
```

Benchmark modes:

- `baseline`: implicit prompt-only comparison saved in every report.
- `--gwt-mode tools`: the model controls GWT tool calls.
- `--gwt-mode controlled`: deterministic benchmark specialists set goals, admit
  query evidence, run broadcast, and produce the final evidence-backed answer.
- `--gwt-mode hybrid`: deterministic GWT routing builds the evidence pack, then
  the model performs final synthesis without a free tool loop.

Controlled benchmark resolvers currently cover RULER advisor chains and
LongBench Pro count/filter/aggregate/top-k employee tasks. They are adapters
over `gwt_context.application.attention.AttentionController`, not product
runtime dependencies.

`--api-path` and `--api-base` are combined deterministically; no hidden path mutation is done in tests.
If your RunPod URL already ends with `/v1`, keep `BENCHMARK_API_PATH=/v1`; the loader will not duplicate the path.

For a Qwen RunPod endpoint with 16 request slots, use:

```dotenv
BENCHMARK_API_BASE=https://example-openai-compatible-endpoint/v1
BENCHMARK_MODEL=qwen3.6-35b-a3b
BENCHMARK_API_KEY=test
BENCHMARK_API_PATH=/v1
BENCHMARK_CONCURRENCY=16
BENCHMARK_TIMEOUT_SECONDS=60
```

## Output behavior

Results are always written under `BENCHMARK_RESULTS_DIR` and filenames are deterministic:

`{benchmark_name}_{safe_model}_{timestamp}_{config_hash}.json`

Each result file is written atomically and contains both:

- task and scoring fields (`gwt_results`, `baseline_results`, accuracy summaries)
- metadata (`run_id`, `run_timestamp`, `api_base`, `config_hash`, `task_count`)
- trace fields (`raw_answer`, `workspace_snapshot`, `workspace_at_answer`, tool/model trace)

Summarize one or more result files with:

```bash
python -m tests.benchmarks.analyze_results tests/benchmarks/results
```

The analyzer reports accuracy, token/latency ratios, workspace occupancy, and
evidence precision/recall when expected evidence metadata is available. It also
reports GWT failure buckets such as `max_tool_rounds`, `tool_markup_as_answer`,
and `wrong_after_tool_loop`.

Run the deterministic regression smoke without model/API calls with:

```bash
python -m tests.benchmarks.regression_smoke
```

Render a trace-heavy JSON result as browsable HTML with:

```bash
python -m tests.benchmarks.render_trace \
  tests/benchmarks/results/<result>.json \
  --output tests/benchmarks/reports/<result>.html
```
