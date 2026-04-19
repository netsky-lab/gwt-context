"""Benchmark harness for GWT-Context.

Runs LLM + GWT tools against benchmark tasks, compares with baseline (no GWT).
Supports any OpenAI-compatible API (Qwen via vLLM, Claude, etc.).

Usage:
    python -m tests.benchmarks.ruler_multi_hop --api-base http://localhost:8000/v1 --model qwen3.5
    python -m tests.benchmarks.longbench_pro --api-base http://localhost:8000/v1 --model qwen3.5
"""

from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass, field
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
    context_chunks: list[str]  # Document chunks to ingest
    expected_answer: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """Result of running one task."""
    task_id: str
    mode: str  # "gwt" or "baseline"
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
            f"Tasks: {len(self.gwt_results)} GWT, {len(self.baseline_results)} baseline",
            f"GWT accuracy:      {self.gwt_accuracy:.1%}",
            f"Baseline accuracy: {self.baseline_accuracy:.1%}",
            f"Improvement:       {self.improvement:+.1f}%",
        ]
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
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


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
            workspace=workspace, competition=competition, broadcast=broadcast,
            buffer=buffer, store=self._store, vector_index=self._vi, goal_manager=goal_manager,
        )

    def execute_tool(self, name: str, args: dict[str, Any]) -> str:
        """Execute a GWT tool call, return result as string."""
        if name == "gwt_store":
            mt = MemoryType(args.get("memory_type", "semantic"))
            item = self._ingestion.ingest(
                content=args["content"], memory_type=mt,
                source="benchmark", link_to=args.get("link_to"),
            )
            self._cycle.buffer.push(item)
            return json.dumps({"id": item.id, "status": "stored"})

        elif name == "gwt_set_goal":
            goal = self._cycle.goal_manager.set_goal(
                description=args["description"],
                keywords=args.get("keywords"),
            )
            return json.dumps({"goal_id": goal.id, "status": "goal set"})

        elif name == "gwt_broadcast":
            record = self._cycle.run()
            return record.formatted_content

        elif name == "gwt_query":
            items = self._ingestion.query_similar(
                query=args["query"], k=args.get("k", 5),
            )
            return json.dumps([
                {"id": i.id, "content": i.content, "activation": round(i.activation_level, 3)}
                for i in items
            ])

        elif name == "gwt_link":
            self._store.add_link(args["source_id"], args["target_id"])
            return json.dumps({"status": "linked"})

        else:
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
        # Pre-load context chunks
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
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
            else:
                # Model produced a text response
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

        # Max rounds reached
        return TaskResult(
            task_id=task.id, mode="gwt",
            predicted_answer="[max tool rounds reached]",
            expected_answer=task.expected_answer,
            correct=False, tool_calls=tool_call_count,
            total_tokens=total_tokens,
            latency_seconds=time.time() - start,
            error="max_tool_rounds",
        )
    except Exception as e:
        return TaskResult(
            task_id=task.id, mode="gwt",
            predicted_answer="", expected_answer=task.expected_answer,
            correct=False, tool_calls=tool_call_count,
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
            task_id=task.id, mode="baseline",
            predicted_answer=predicted,
            expected_answer=task.expected_answer,
            correct=correct, tool_calls=0,
            total_tokens=total_tokens,
            latency_seconds=time.time() - start,
        )
    except Exception as e:
        return TaskResult(
            task_id=task.id, mode="baseline",
            predicted_answer="", expected_answer=task.expected_answer,
            correct=False, tool_calls=0, total_tokens=0,
            latency_seconds=time.time() - start,
            error=str(e),
        )


def run_benchmark(
    benchmark_name: str,
    tasks: list[BenchmarkTask],
    api_base: str,
    model: str,
    api_key: str = "not-needed",
    max_tasks: int | None = None,
    results_dir: Path = Path("tests/benchmarks/results"),
) -> BenchmarkReport:
    """Run full benchmark: GWT + baseline for each task."""
    client = OpenAI(base_url=api_base, api_key=api_key)
    embedder = SentenceTransformerEmbedder()

    if max_tasks:
        tasks = tasks[:max_tasks]

    report = BenchmarkReport(benchmark_name=benchmark_name, model=model)

    for i, task in enumerate(tasks):
        print(f"[{i+1}/{len(tasks)}] Task {task.id}...")

        # GWT mode
        result_gwt = run_task_gwt(client, model, task, embedder)
        report.results.append(result_gwt)
        status = "OK" if result_gwt.correct else "WRONG"
        print(
            "  GWT:      "
            f"{status} ({result_gwt.tool_calls} calls, {result_gwt.latency_seconds:.1f}s)"
        )

        # Baseline mode
        result_bl = run_task_baseline(client, model, task)
        report.results.append(result_bl)
        status = "OK" if result_bl.correct else "WRONG"
        print(f"  Baseline: {status} ({result_bl.latency_seconds:.1f}s)")

    print()
    print(report.summary())

    # Save results
    ts = time.strftime("%Y%m%d_%H%M%S")
    report.save(results_dir / f"{benchmark_name}_{model}_{ts}.json")

    return report


# --- Helpers ---

def _extract_answer(text: str) -> str:
    """Extract answer after 'ANSWER:' marker."""
    text = text.strip()
    if "ANSWER:" in text:
        return text.split("ANSWER:")[-1].strip()
    # Fallback: last line
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return lines[-1] if lines else text


def _check_answer(predicted: str, expected: str) -> bool:
    """Check if predicted answer matches expected (case-insensitive, substring)."""
    predicted = predicted.lower().strip()
    expected = expected.lower().strip()
    # Exact match or expected is contained in predicted
    return expected in predicted or predicted in expected
