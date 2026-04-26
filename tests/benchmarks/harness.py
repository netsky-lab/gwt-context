"""Benchmark harness for GWT-Context.

Runs LLM + GWT tools against benchmark tasks, compares with baseline (no GWT).
Supports any OpenAI-compatible API (Qwen via vLLM, Claude, etc.).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from gwt_context.application.cycle import PreconsciousBuffer, SelectionBroadcastCycle
from gwt_context.application.goal_manager import GoalManager
from gwt_context.application.ingestion import IngestionPipeline
from gwt_context.domain.broadcast import BroadcastAssembler
from gwt_context.domain.competition import CompetitionEngine
from gwt_context.domain.models import MemoryType
from gwt_context.domain.specialists import create_default_specialists
from gwt_context.domain.workspace import GlobalWorkspace
from gwt_context.infrastructure.config import GWTConfig
from gwt_context.infrastructure.embeddings import SentenceTransformerEmbedder
from gwt_context.infrastructure.storage import SQLiteMemoryStore
from gwt_context.infrastructure.vector_index import VectorIndex
from tests.benchmarks.config import (
    BenchmarkConfig,
    load_benchmark_config,
)

# --- GWT Tool Definitions (OpenAI function calling format) ---

GWT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "gwt_store",
            "description": (
                "Store information in long-term memory. Use to save facts, "
                "observations, intermediate reasoning."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Text to store"},
                    "memory_type": {
                        "type": "string",
                        "enum": ["episodic", "semantic", "procedural", "working"],
                        "default": "semantic",
                    },
                    "link_to": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of items to link to",
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gwt_set_goal",
            "description": "Set the active goal. Biases competition toward goal-relevant items.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Natural language objective"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gwt_broadcast",
            "description": (
                "Run selection-broadcast cycle. Returns workspace with most "
                "relevant items. Call before reasoning."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gwt_query",
            "description": (
                "Search long-term memory by semantic similarity. "
                "Returns items without admitting to workspace."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gwt_link",
            "description": (
                "Link two memory items bidirectionally. "
                "Linked items boost each other in competition."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "target_id": {"type": "string"},
                },
                "required": ["source_id", "target_id"],
            },
        },
    },
]


# --- Data classes ---


@dataclass
class BenchmarkTask:
    """A single benchmark task."""

    id: str
    question: str
    context_chunks: list[str]
    expected_answer: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """Result of running one task."""

    task_id: str
    mode: str
    predicted_answer: str
    expected_answer: str
    correct: bool
    tool_calls: int
    total_tokens: int
    latency_seconds: float
    workspace_at_answer: str = ""
    error: str = ""


@dataclass
class BenchmarkReport:
    """Aggregated benchmark results."""

    benchmark_name: str
    model: str
    results: list[TaskResult] = field(default_factory=list)
    run_id: str = ""
    run_timestamp: str = ""
    api_base: str = ""
    results_dir: str = ""
    config_hash: str = ""
    task_count: int = 0

    @property
    def gwt_results(self) -> list[TaskResult]:
        return [r for r in self.results if r.mode == "gwt"]

    @property
    def baseline_results(self) -> list[TaskResult]:
        return [r for r in self.results if r.mode == "baseline"]

    @property
    def gwt_accuracy(self) -> float:
        gwt = self.gwt_results
        if not gwt:
            return 0.0
        return sum(1 for r in gwt if r.correct) / len(gwt)

    @property
    def baseline_accuracy(self) -> float:
        bl = self.baseline_results
        if not bl:
            return 0.0
        return sum(1 for r in bl if r.correct) / len(bl)

    @property
    def improvement(self) -> float:
        if self.baseline_accuracy == 0:
            return 0.0
        return (self.gwt_accuracy - self.baseline_accuracy) / self.baseline_accuracy * 100

    def summary(self) -> str:
        lines = [
            f"=== {self.benchmark_name} | model={self.model} ===",
            f"Run ID: {self.run_id}",
            f"Timestamp: {self.run_timestamp}",
            f"Tasks: {len(self.gwt_results)} GWT, {len(self.baseline_results)} baseline",
            f"GWT accuracy:      {self.gwt_accuracy:.1%}",
            f"Baseline accuracy: {self.baseline_accuracy:.1%}",
            f"Improvement:       {self.improvement:+.1f}%",
        ]
        if self.task_count:
            lines.append(f"Task count: {self.task_count}")
        if self.gwt_results:
            avg_calls = sum(r.tool_calls for r in self.gwt_results) / len(self.gwt_results)
            avg_latency = sum(r.latency_seconds for r in self.gwt_results) / len(self.gwt_results)
            lines.append(f"Avg tool calls:    {avg_calls:.1f}")
            lines.append(f"Avg latency:       {avg_latency:.1f}s")
        return "\n".join(lines)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "benchmark_name": self.benchmark_name,
            "model": self.model,
            "run_id": self.run_id,
            "run_timestamp": self.run_timestamp,
            "api_base": self.api_base,
            "results_dir": self.results_dir,
            "config_hash": self.config_hash,
            "task_count": self.task_count,
            "gwt_accuracy": self.gwt_accuracy,
            "baseline_accuracy": self.baseline_accuracy,
            "improvement": self.improvement,
            "results": [
                {
                    "task_id": r.task_id,
                    "mode": r.mode,
                    "predicted": r.predicted_answer,
                    "expected": r.expected_answer,
                    "correct": r.correct,
                    "tool_calls": r.tool_calls,
                    "total_tokens": r.total_tokens,
                    "latency_seconds": r.latency_seconds,
                    "error": r.error,
                }
                for r in self.results
            ],
        }
        _write_json_atomically(path, data)


# --- GWT Session ---


class GWTSession:
    """A fresh GWT system for one benchmark task."""

    def __init__(self, config: GWTConfig | None = None) -> None:
        self._tmp = tempfile.mkdtemp()
        if config is None:
            config = GWTConfig(data_dir=self._tmp)
        else:
            config.data_dir = self._tmp
        config.ensure_data_dir()

        self._embedder = SentenceTransformerEmbedder(model_name=config.embedding_model)
        self._store = SQLiteMemoryStore(db_path=config.db_path)
        self._vi = VectorIndex(dim=config.embedding_dim, path=config.vector_index_path)

        workspace = GlobalWorkspace(capacity=config.workspace_capacity)
        specialists = create_default_specialists()
        competition = CompetitionEngine(
            specialists=specialists,
            goal_modulation_strength=config.goal_modulation_strength,
        )
        broadcast = BroadcastAssembler(max_tokens=config.max_broadcast_tokens)
        buffer = PreconsciousBuffer(max_size=config.buffer_size)
        goal_manager = GoalManager(store=self._store, embedder=self._embedder)

        self._ingestion = IngestionPipeline(
            store=self._store,
            vector_index=self._vi,
            embedder=self._embedder,
        )
        self._cycle = SelectionBroadcastCycle(
            workspace=workspace,
            competition=competition,
            broadcast=broadcast,
            buffer=buffer,
            store=self._store,
            vector_index=self._vi,
            goal_manager=goal_manager,
        )

    def execute_tool(self, name: str, args: dict[str, Any]) -> str:
        """Execute a GWT tool call, return result as string."""
        if name == "gwt_store":
            mt = MemoryType(args.get("memory_type", "semantic"))
            item = self._ingestion.ingest(
                content=args["content"],
                memory_type=mt,
                source="benchmark",
                link_to=args.get("link_to"),
            )
            self._cycle.buffer.push(item)
            return json.dumps({"id": item.id, "status": "stored"})

        if name == "gwt_set_goal":
            goal = self._cycle.goal_manager.set_goal(
                description=args["description"],
                keywords=args.get("keywords"),
            )
            return json.dumps({"goal_id": goal.id, "status": "goal set"})

        if name == "gwt_broadcast":
            record = self._cycle.run()
            return record.formatted_content

        if name == "gwt_query":
            items = self._ingestion.query_similar(
                query=args["query"],
                k=args.get("k", 5),
            )
            return json.dumps(
                [
                    {"id": i.id, "content": i.content, "activation": round(i.activation_level, 3)}
                    for i in items
                ]
            )

        if name == "gwt_link":
            self._store.add_link(args["source_id"], args["target_id"])
            return json.dumps({"status": "linked"})

        return json.dumps({"error": f"unknown tool: {name}"})

    @property
    def workspace_text(self) -> str:
        return self._cycle.workspace.get_broadcast_text()

    def close(self) -> None:
        self._store.close()
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)


# --- Runner ---

GWT_SYSTEM_PROMPT = """You have access to a Global Workspace Theory (GWT) memory system.

WORKFLOW:
1. Call gwt_set_goal with the question you need to answer
2. Call gwt_broadcast to get the most relevant context from memory
3. If needed, call gwt_query to search for specific information
4. Use gwt_store to save intermediate reasoning results (memory_type="working")
5. Use gwt_link to connect related facts for multi-hop reasoning
6. Call gwt_broadcast again to refresh context with linked items
7. Give your final answer

IMPORTANT: After reasoning, provide your final answer in the format:
ANSWER: <your answer>
"""

MAX_TOOL_ROUNDS = 10


def run_task_gwt(
    client: OpenAI,
    model: str,
    task: BenchmarkTask,
    embedder: SentenceTransformerEmbedder,
) -> TaskResult:
    """Run a single task with GWT tools."""
    session = GWTSession()
    start = time.time()
    tool_call_count = 0
    total_tokens = 0

    try:
        for chunk in task.context_chunks:
            session.execute_tool("gwt_store", {"content": chunk})

        messages = [
            {"role": "system", "content": GWT_SYSTEM_PROMPT},
            {"role": "user", "content": task.question},
        ]

        for _ in range(MAX_TOOL_ROUNDS):
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=GWT_TOOLS,
                tool_choice="auto",
            )

            choice = response.choices[0]
            total_tokens += (response.usage.total_tokens if response.usage else 0)

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                messages.append(choice.message)
                for tc in choice.message.tool_calls:
                    tool_call_count += 1
                    args = json.loads(tc.function.arguments)
                    result = session.execute_tool(tc.function.name, args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        }
                    )
            else:
                answer_text = choice.message.content or ""
                predicted = _extract_answer(answer_text)
                correct = _check_answer(predicted, task.expected_answer)

                return TaskResult(
                    task_id=task.id,
                    mode="gwt",
                    predicted_answer=predicted,
                    expected_answer=task.expected_answer,
                    correct=correct,
                    tool_calls=tool_call_count,
                    total_tokens=total_tokens,
                    latency_seconds=time.time() - start,
                    workspace_at_answer=session.workspace_text,
                )

        return TaskResult(
            task_id=task.id,
            mode="gwt",
            predicted_answer="[max tool rounds reached]",
            expected_answer=task.expected_answer,
            correct=False,
            tool_calls=tool_call_count,
            total_tokens=total_tokens,
            latency_seconds=time.time() - start,
            error="max_tool_rounds",
        )
    except Exception as e:
        return TaskResult(
            task_id=task.id,
            mode="gwt",
            predicted_answer="",
            expected_answer=task.expected_answer,
            correct=False,
            tool_calls=tool_call_count,
            total_tokens=total_tokens,
            latency_seconds=time.time() - start,
            error=str(e),
        )
    finally:
        session.close()


def run_task_baseline(
    client: OpenAI,
    model: str,
    task: BenchmarkTask,
) -> TaskResult:
    """Run a single task WITHOUT GWT — all context in prompt."""
    start = time.time()
    context = "\n\n".join(task.context_chunks)
    messages = [
        {
            "role": "system",
            "content": (
                "Answer the question based on the provided context. "
                "End with ANSWER: <your answer>"
            ),
        },
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {task.question}"},
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
        )
        answer_text = response.choices[0].message.content or ""
        total_tokens = response.usage.total_tokens if response.usage else 0
        predicted = _extract_answer(answer_text)
        correct = _check_answer(predicted, task.expected_answer)

        return TaskResult(
            task_id=task.id,
            mode="baseline",
            predicted_answer=predicted,
            expected_answer=task.expected_answer,
            correct=correct,
            tool_calls=0,
            total_tokens=total_tokens,
            latency_seconds=time.time() - start,
        )
    except Exception as e:
        return TaskResult(
            task_id=task.id,
            mode="baseline",
            predicted_answer="",
            expected_answer=task.expected_answer,
            correct=False,
            tool_calls=0,
            total_tokens=0,
            latency_seconds=time.time() - start,
            error=str(e),
        )


def _safe_filename_component(value: str) -> str:
    """Normalize values used in file names."""
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)


def _report_config_hash(config: BenchmarkConfig) -> str:
    payload = {
        "api_base": config.api_base,
        "model": config.model,
        "timeout_seconds": config.timeout_seconds,
        "max_retries": config.max_retries,
        "concurrency": config.concurrency,
        "api_headers": config.api_headers,
        "results_dir": config.results_dir,
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def _write_json_atomically(path: Path, data: dict[str, Any]) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    temp_path.replace(path)


def _build_openai_client(config: BenchmarkConfig) -> OpenAI:
    kwargs = {
        "api_key": config.api_key,
        "base_url": config.api_base,
        "timeout": config.timeout_seconds,
        "max_retries": config.max_retries,
    }
    if config.api_headers:
        kwargs["default_headers"] = config.api_headers
    return OpenAI(**kwargs)


def _resolve_benchmark_config(
    *,
    base_config: BenchmarkConfig | None,
    api_base: str | None,
    model: str | None,
    api_key: str,
    api_path: str | None,
    timeout_seconds: str | float | int | None,
    api_headers: str | None,
    results_dir: Path | str,
    max_retries: int | None,
    concurrency: int | None,
) -> BenchmarkConfig:
    if base_config is None:
        return load_benchmark_config(
            api_base=api_base,
            model=model,
            api_key=api_key,
            api_path=api_path,
            timeout_seconds=timeout_seconds,
            api_headers=api_headers,
            results_dir=results_dir,
            max_retries=max_retries,
            concurrency=concurrency,
        )

    return load_benchmark_config(
        api_base=api_base or base_config.api_base,
        model=model or base_config.model,
        api_key=api_key or base_config.api_key,
        api_path=api_path if api_path is not None else base_config.api_path,
        timeout_seconds=(
            timeout_seconds if timeout_seconds is not None else base_config.timeout_seconds
        ),
        api_headers=api_headers if api_headers is not None else json.dumps(base_config.api_headers),
        results_dir=results_dir if results_dir is not None else base_config.results_dir,
        max_retries=max_retries if max_retries is not None else base_config.max_retries,
        concurrency=concurrency if concurrency is not None else base_config.concurrency,
    )


def run_benchmark(
    benchmark_name: str,
    tasks: list[BenchmarkTask],
    *,
    api_base: str | None = None,
    model: str | None = None,
    api_key: str = "not-needed",
    api_path: str | None = None,
    timeout_seconds: str | float | int | None = None,
    api_headers: str | None = None,
    results_dir: Path | str = Path("tests/benchmarks/results"),
    max_tasks: int | None = None,
    max_retries: int | None = None,
    concurrency: int | None = None,
    config: BenchmarkConfig | None = None,
) -> BenchmarkReport:
    """Run full benchmark: GWT + baseline for each task."""
    config = _resolve_benchmark_config(
        base_config=config,
        api_base=api_base,
        model=model,
        api_key=api_key,
        api_path=api_path,
        timeout_seconds=timeout_seconds,
        api_headers=api_headers,
        results_dir=results_dir,
        max_retries=max_retries,
        concurrency=concurrency,
    )

    client = _build_openai_client(config)
    embedder = SentenceTransformerEmbedder()

    if max_tasks is not None:
        if max_tasks <= 0:
            raise ValueError("--max-tasks must be greater than 0")
        tasks = tasks[:max_tasks]

    run_config_hash = _report_config_hash(config)
    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    report = BenchmarkReport(
        benchmark_name=benchmark_name,
        model=config.model,
        run_id=f"{run_timestamp}_{run_config_hash}",
        run_timestamp=run_timestamp,
        api_base=config.api_base,
        results_dir=config.results_dir,
        config_hash=run_config_hash,
        task_count=len(tasks),
    )

    def run_task_pair(index: int, task: BenchmarkTask) -> tuple[int, TaskResult, TaskResult]:
        result_gwt = run_task_gwt(client, config.model, task, embedder)
        result_bl = run_task_baseline(client, config.model, task)
        return index, result_gwt, result_bl

    task_results: list[tuple[TaskResult, TaskResult] | None] = [None] * len(tasks)
    if config.concurrency == 1:
        for i, task in enumerate(tasks):
            print(f"[{i+1}/{len(tasks)}] Task {task.id}...")
            index, result_gwt, result_bl = run_task_pair(i, task)
            task_results[index] = (result_gwt, result_bl)
            _print_task_result(result_gwt, result_bl)
    else:
        print(f"Running with concurrency={config.concurrency}")
        with ThreadPoolExecutor(max_workers=config.concurrency) as executor:
            futures = {
                executor.submit(run_task_pair, i, task): (i, task)
                for i, task in enumerate(tasks)
            }
            for future in as_completed(futures):
                i, task = futures[future]
                index, result_gwt, result_bl = future.result()
                task_results[index] = (result_gwt, result_bl)
                print(f"[{i+1}/{len(tasks)}] Task {task.id} complete")
                _print_task_result(result_gwt, result_bl)

    for result_pair in task_results:
        if result_pair is None:
            continue
        result_gwt, result_bl = result_pair
        report.results.append(result_gwt)
        report.results.append(result_bl)

    print()
    print(report.summary())

    # Keep filename deterministic and non-overlapping by using run metadata.
    out_dir = Path(config.results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_model = _safe_filename_component(config.model)
    filename_id = f"{report.run_timestamp}_{report.config_hash}"
    output_path = out_dir / f"{benchmark_name}_{safe_model}_{filename_id}.json"
    report.save(output_path)

    print(f"Saved: {output_path}")

    return report


# --- Helpers ---


def _extract_answer(text: str) -> str:
    """Extract answer after 'ANSWER:' marker."""
    text = text.strip()
    if "ANSWER:" in text:
        return text.split("ANSWER:")[-1].strip()
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return lines[-1] if lines else text


def _print_task_result(result_gwt: TaskResult, result_bl: TaskResult) -> None:
    gwt_status = "OK" if result_gwt.correct else "WRONG"
    print(
        "  GWT:      "
        f"{gwt_status} ({result_gwt.tool_calls} calls, {result_gwt.latency_seconds:.1f}s)"
    )
    baseline_status = "OK" if result_bl.correct else "WRONG"
    print(f"  Baseline: {baseline_status} ({result_bl.latency_seconds:.1f}s)")


def _check_answer(predicted: str, expected: str) -> bool:
    """Check if predicted answer matches expected (case-insensitive, substring)."""
    predicted = predicted.lower().strip()
    expected = expected.lower().strip()
    return expected in predicted or predicted in expected
