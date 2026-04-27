"""Benchmark harness for GWT-Context.

Runs LLM + GWT tools against benchmark tasks, compares with baseline (no GWT).
Supports any OpenAI-compatible API (Qwen via vLLM, Claude, etc.).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from gwt_context.application.attention import (
    AttentionController,
    AttentionRun,
    EvidencePlan,
    GenericEvidenceResolver,
    evidence_plan_to_dict,
    extract_question_keywords,
)
from gwt_context.application.cycle import PreconsciousBuffer, SelectionBroadcastCycle
from gwt_context.application.goal_manager import GoalManager
from gwt_context.application.ingestion import IngestionPipeline
from gwt_context.domain.broadcast import BroadcastAssembler
from gwt_context.domain.competition import CompetitionEngine
from gwt_context.domain.models import MemoryType
from gwt_context.domain.specialists import create_default_specialists
from gwt_context.domain.workspace import GlobalWorkspace
from gwt_context.infrastructure.config import GWTConfig
from gwt_context.infrastructure.embeddings import HashEmbeddingEmbedder, SentenceTransformerEmbedder
from gwt_context.infrastructure.storage import SQLiteMemoryStore
from gwt_context.infrastructure.vector_index import VectorIndex
from gwt_context.interfaces.ports import EmbeddingPort
from tests.benchmarks.config import (
    BenchmarkConfig,
    load_benchmark_config,
)
from tests.benchmarks.controlled_rules import (
    build_benchmark_resolvers,
    resolve_benchmark_evidence_dict,
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
                "Set admit=true to enqueue returned items for workspace competition."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "default": 5},
                    "admit": {
                        "type": "boolean",
                        "default": False,
                        "description": "Whether to admit returned items into competition.",
                    },
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
    raw_answer: str = ""
    workspace_at_answer: str = ""
    workspace_snapshot: dict[str, Any] = field(default_factory=dict)
    trace: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    task_metadata: dict[str, Any] = field(default_factory=dict)
    expected_evidence: list[str] = field(default_factory=list)


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
    gwt_mode: str = "tools"

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

    @property
    def avg_gwt_tokens(self) -> float:
        return _average_result_field(self.gwt_results, "total_tokens")

    @property
    def avg_baseline_tokens(self) -> float:
        return _average_result_field(self.baseline_results, "total_tokens")

    @property
    def avg_gwt_latency(self) -> float:
        return _average_result_field(self.gwt_results, "latency_seconds")

    @property
    def avg_baseline_latency(self) -> float:
        return _average_result_field(self.baseline_results, "latency_seconds")

    @property
    def avg_workspace_occupied(self) -> float:
        counts = [
            result.workspace_snapshot.get("workspace", {}).get("occupied_count", 0)
            for result in self.gwt_results
        ]
        if not counts:
            return 0.0
        return sum(float(count) for count in counts) / len(counts)

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
            "gwt_mode": self.gwt_mode,
            "gwt_accuracy": self.gwt_accuracy,
            "baseline_accuracy": self.baseline_accuracy,
            "improvement": self.improvement,
            "avg_gwt_tokens": self.avg_gwt_tokens,
            "avg_baseline_tokens": self.avg_baseline_tokens,
            "avg_gwt_latency": self.avg_gwt_latency,
            "avg_baseline_latency": self.avg_baseline_latency,
            "avg_workspace_occupied": self.avg_workspace_occupied,
            "avg_evidence_precision": _average_result_metric(
                self.gwt_results,
                "precision",
            ),
            "avg_evidence_recall": _average_result_metric(
                self.gwt_results,
                "recall",
            ),
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
                    "raw_answer": r.raw_answer,
                    "workspace_at_answer": r.workspace_at_answer,
                    "workspace_snapshot": r.workspace_snapshot,
                    "trace": r.trace,
                    "error": r.error,
                    "task_metadata": r.task_metadata,
                    "expected_evidence": r.expected_evidence,
                    "evidence_available": _result_evidence_metrics(r)["available"],
                    "evidence_precision": _result_evidence_metrics(r)["precision"],
                    "evidence_recall": _result_evidence_metrics(r)["recall"],
                }
                for r in self.results
            ],
        }
        _write_json_atomically(path, data)


# --- GWT Session ---


class GWTSession:
    """A fresh GWT system for one benchmark task."""

    def __init__(
        self,
        config: GWTConfig | None = None,
        embedder: EmbeddingPort | None = None,
    ) -> None:
        self._tmp = tempfile.mkdtemp()
        if config is None:
            config = GWTConfig.from_env()
            config.data_dir = self._tmp
        else:
            config.data_dir = self._tmp
        config.db_path_override = None
        config.vector_index_path_override = None
        config.ensure_data_dir()

        self._embedder = embedder or _build_benchmark_embedder(config)
        self._store = SQLiteMemoryStore(db_path=config.db_path)
        self._vi = VectorIndex(dim=config.embedding_dim, path=None)

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
        result, _trace = self.execute_tool_with_trace(name, args)
        return result

    def execute_tool_with_trace(
        self,
        name: str,
        args: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Execute a GWT tool call and return a JSON-serializable trace payload."""
        trace: dict[str, Any] = {
            "tool": name,
            "arguments": args,
        }
        if name == "gwt_store":
            if "content" not in args:
                return _tool_error(name, "missing required argument: content", trace)
            mt = MemoryType(args.get("memory_type", "semantic"))
            item = self._ingestion.ingest(
                content=args["content"],
                memory_type=mt,
                source="benchmark",
                link_to=args.get("link_to"),
            )
            self._cycle.enqueue_for_competition(item)
            payload = {"id": item.id, "status": "stored"}
            trace["result"] = payload
            trace["buffer_after"] = self._cycle.inspect("buffer")
            return json.dumps(payload), trace

        if name == "gwt_set_goal":
            if "description" not in args:
                return _tool_error(name, "missing required argument: description", trace)
            goal = self._cycle.set_goal(
                description=args["description"],
                keywords=args.get("keywords"),
            )
            payload = {"goal_id": goal.id, "status": "goal set"}
            trace["result"] = payload
            trace["goals_after"] = self._cycle.inspect("goals")
            return json.dumps(payload), trace

        if name == "gwt_broadcast":
            dry_run = self._cycle.run_competition_dry()
            trace["competition"] = _competition_trace(dry_run)
            record = self._cycle.run()
            trace["result"] = {
                "id": record.id,
                "admitted": record.admitted_ids,
                "evicted": record.evicted_ids,
            }
            trace["workspace_after"] = self._cycle.inspect("workspace")
            return record.formatted_content, trace

        if name == "gwt_query":
            if "query" not in args:
                return _tool_error(name, "missing required argument: query", trace)
            items = self._ingestion.query_similar(
                query=args["query"],
                k=args.get("k", 5),
            )
            admitted_ids = []
            if args.get("admit"):
                for item in items:
                    self._cycle.enqueue_for_competition(item)
                    admitted_ids.append(item.id)
            payload = [
                {"id": i.id, "content": i.content, "activation": round(i.activation_level, 3)}
                for i in items
            ]
            trace["result"] = payload
            trace["admitted_ids"] = admitted_ids
            return json.dumps(payload), trace

        if name == "gwt_link":
            if "source_id" not in args or "target_id" not in args:
                return _tool_error(
                    name,
                    "missing required arguments: source_id and target_id",
                    trace,
                )
            payload = self._cycle.link_items(args["source_id"], args["target_id"])
            trace["result"] = payload
            trace["workspace_after"] = self._cycle.inspect("workspace")
            trace["buffer_after"] = self._cycle.inspect("buffer")
            return json.dumps(payload), trace

        payload = {"error": f"unknown tool: {name}"}
        trace["result"] = payload
        return json.dumps(payload), trace

    @property
    def workspace_text(self) -> str:
        return self._cycle.get_workspace_broadcast()

    def snapshot(self) -> dict[str, Any]:
        """Return a read-model snapshot of the current benchmark GWT session."""
        return {
            "workspace": self._cycle.inspect("workspace"),
            "buffer": self._cycle.inspect("buffer"),
            "goals": self._cycle.inspect("goals"),
            "stats": self._cycle.inspect("stats"),
        }

    @property
    def cycle(self) -> SelectionBroadcastCycle:
        """Application cycle used by benchmark controllers."""
        return self._cycle

    @property
    def ingestion(self) -> IngestionPipeline:
        """Application ingestion service used by benchmark controllers."""
        return self._ingestion

    def close(self) -> None:
        self._store.close()
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)


def _build_benchmark_embedder(config: GWTConfig) -> EmbeddingPort:
    provider = config.embedding_provider.lower().strip()
    model_name = config.embedding_model.lower().strip()
    if provider in {"hash", "deterministic", "local-hash"} or model_name in {
        "hash",
        "deterministic",
        "local-hash",
    }:
        return HashEmbeddingEmbedder(dim=config.embedding_dim)
    return SentenceTransformerEmbedder(model_name=config.embedding_model)


# --- Runner ---

GWT_SYSTEM_PROMPT = """You have access to a Global Workspace Theory (GWT) memory system.

Use the tools as an active working-memory loop, not as optional search.

Required workflow:
1. First call gwt_set_goal with the exact question and useful keywords.
2. Call gwt_query with admit=true for the key entity/attribute in the question.
3. Call gwt_broadcast to admit the most relevant facts into the workspace.
4. If the answer needs multiple hops, call gwt_query or gwt_link, then gwt_broadcast again.
5. Answer only from the question and broadcast/query evidence.

IMPORTANT: Finish with exactly this format:
ANSWER: <your answer>
Do not print tool-call markup as text. If you need a tool, use the official tool call channel.
"""

MAX_TOOL_ROUNDS = 10
ATTEND_PASSES = max(1, int(os.getenv("BENCHMARK_ATTEND_PASSES", "1")))

HYBRID_SYSTEM_PROMPT = """Answer from the supplied GWT workspace evidence only.

Do not call tools. Do not use outside knowledge. Finish with exactly:
ANSWER: <your answer>
"""


def run_task_gwt(
    client: OpenAI,
    model: str,
    task: BenchmarkTask,
    embedder: EmbeddingPort,
) -> TaskResult:
    """Run a single task with GWT tools."""
    session = GWTSession(embedder=embedder)
    start = time.time()
    tool_call_count = 0
    total_tokens = 0
    trace: list[dict[str, Any]] = []

    try:
        for chunk in task.context_chunks:
            _result, tool_trace = session.execute_tool_with_trace("gwt_store", {"content": chunk})
            tool_trace["phase"] = "preload"
            trace.append(tool_trace)

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
            trace.append(
                {
                    "phase": "model",
                    "round": len([entry for entry in trace if entry.get("phase") == "model"]) + 1,
                    "finish_reason": choice.finish_reason,
                    "content": choice.message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                        for tc in (choice.message.tool_calls or [])
                    ],
                }
            )

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                messages.append(choice.message)
                for tc in choice.message.tool_calls:
                    tool_call_count += 1
                    args = json.loads(tc.function.arguments)
                    result, tool_trace = session.execute_tool_with_trace(tc.function.name, args)
                    tool_trace["phase"] = "tool"
                    tool_trace["round"] = tool_call_count
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        }
                    )
                    trace.append(tool_trace)
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
                    raw_answer=answer_text,
                    workspace_at_answer=session.workspace_text,
                    workspace_snapshot=session.snapshot(),
                    trace=trace,
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
            workspace_at_answer=session.workspace_text,
            workspace_snapshot=session.snapshot(),
            trace=trace,
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
            workspace_at_answer=session.workspace_text,
            workspace_snapshot=session.snapshot(),
            trace=trace,
            error=str(e),
        )
    finally:
        session.close()


def run_task_gwt_controlled(
    client: OpenAI,
    model: str,
    task: BenchmarkTask,
    embedder: EmbeddingPort,
) -> TaskResult:
    """Run a task with a deterministic GWT controller and specialist evidence."""
    del client, model
    session = GWTSession(embedder=embedder)
    start = time.time()
    trace: list[dict[str, Any]] = []
    tool_call_count = 0

    try:
        for chunk in task.context_chunks:
            _result, tool_trace = session.execute_tool_with_trace("gwt_store", {"content": chunk})
            tool_trace["phase"] = "preload"
            trace.append(tool_trace)

        controller_run = _run_controlled_controller(session, task, trace)
        evidence = controller_run.evidence
        tool_call_count = controller_run.tool_call_count

        predicted = evidence.answer
        raw_answer = _format_controlled_answer(task.question, evidence)

        return TaskResult(
            task_id=task.id,
            mode="gwt",
            predicted_answer=predicted,
            expected_answer=task.expected_answer,
            correct=_check_answer(predicted, task.expected_answer),
            tool_calls=tool_call_count,
            total_tokens=0,
            latency_seconds=time.time() - start,
            raw_answer=raw_answer,
            workspace_at_answer=session.workspace_text,
            workspace_snapshot=session.snapshot(),
            trace=trace,
        )
    except Exception as e:
        return TaskResult(
            task_id=task.id,
            mode="gwt",
            predicted_answer="",
            expected_answer=task.expected_answer,
            correct=False,
            tool_calls=tool_call_count,
            total_tokens=0,
            latency_seconds=time.time() - start,
            workspace_at_answer=session.workspace_text,
            workspace_snapshot=session.snapshot(),
            trace=trace,
            error=str(e),
        )
    finally:
        session.close()


def run_task_gwt_hybrid(
    client: OpenAI,
    model: str,
    task: BenchmarkTask,
    embedder: EmbeddingPort,
) -> TaskResult:
    """Run deterministic GWT routing, then ask the model for final synthesis."""
    session = GWTSession(embedder=embedder)
    start = time.time()
    trace: list[dict[str, Any]] = []
    tool_call_count = 0
    total_tokens = 0

    try:
        for chunk in task.context_chunks:
            _result, tool_trace = session.execute_tool_with_trace("gwt_store", {"content": chunk})
            tool_trace["phase"] = "preload"
            trace.append(tool_trace)

        controller_run = _run_controlled_controller(session, task, trace)
        evidence = controller_run.evidence
        tool_call_count += controller_run.tool_call_count

        prompt = _format_hybrid_prompt(task.question, evidence)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": HYBRID_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        total_tokens = response.usage.total_tokens if response.usage else 0
        answer_text = response.choices[0].message.content or ""
        predicted = _extract_answer(answer_text)
        trace.append(
            {
                "phase": "hybrid_model",
                "content": answer_text,
                "finish_reason": response.choices[0].finish_reason,
                "prompt": prompt,
            }
        )

        return TaskResult(
            task_id=task.id,
            mode="gwt",
            predicted_answer=predicted,
            expected_answer=task.expected_answer,
            correct=_check_answer(predicted, task.expected_answer),
            tool_calls=tool_call_count,
            total_tokens=total_tokens,
            latency_seconds=time.time() - start,
            raw_answer=answer_text,
            workspace_at_answer=session.workspace_text,
            workspace_snapshot=session.snapshot(),
            trace=trace,
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
            workspace_at_answer=session.workspace_text,
            workspace_snapshot=session.snapshot(),
            trace=trace,
            error=str(e),
        )
    finally:
        session.close()


def run_task_gwt_attend(
    client: OpenAI,
    model: str,
    task: BenchmarkTask,
    embedder: EmbeddingPort,
) -> TaskResult:
    """Run production generic attention routing, then ask the model to synthesize."""
    session = GWTSession(embedder=embedder)
    start = time.time()
    trace: list[dict[str, Any]] = []
    tool_call_count = 0
    total_tokens = 0

    try:
        for chunk in task.context_chunks:
            _result, tool_trace = session.execute_tool_with_trace("gwt_store", {"content": chunk})
            tool_trace["phase"] = "preload"
            trace.append(tool_trace)

        controller_run = _run_attend_controller(session, task, trace)
        evidence = controller_run.evidence
        tool_call_count += controller_run.tool_call_count

        if evidence.metadata.get("deterministic_answer") and evidence.answer:
            raw_answer = _format_controlled_answer(task.question, evidence)
            trace.append(
                {
                    "phase": "attend_controller_answer",
                    "content": raw_answer,
                    "strategy": evidence.strategy,
                }
            )
            return TaskResult(
                task_id=task.id,
                mode="gwt",
                predicted_answer=evidence.answer,
                expected_answer=task.expected_answer,
                correct=_check_answer(evidence.answer, task.expected_answer),
                tool_calls=tool_call_count,
                total_tokens=0,
                latency_seconds=time.time() - start,
                raw_answer=raw_answer,
                workspace_at_answer=session.workspace_text,
                workspace_snapshot=session.snapshot(),
                trace=trace,
            )

        prompt = _format_attend_prompt(task.question, evidence, session.workspace_text)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": HYBRID_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        total_tokens = response.usage.total_tokens if response.usage else 0
        answer_text = response.choices[0].message.content or ""
        predicted = _extract_answer(answer_text)
        trace.append(
            {
                "phase": "attend_model",
                "content": answer_text,
                "finish_reason": response.choices[0].finish_reason,
                "prompt": prompt,
            }
        )

        return TaskResult(
            task_id=task.id,
            mode="gwt",
            predicted_answer=predicted,
            expected_answer=task.expected_answer,
            correct=_check_answer(predicted, task.expected_answer),
            tool_calls=tool_call_count,
            total_tokens=total_tokens,
            latency_seconds=time.time() - start,
            raw_answer=answer_text,
            workspace_at_answer=session.workspace_text,
            workspace_snapshot=session.snapshot(),
            trace=trace,
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
            workspace_at_answer=session.workspace_text,
            workspace_snapshot=session.snapshot(),
            trace=trace,
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
            raw_answer=answer_text,
            trace=[
                {
                    "phase": "model",
                    "content": answer_text,
                    "finish_reason": response.choices[0].finish_reason,
                }
            ],
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
    gwt_mode: str = "tools",
    config: BenchmarkConfig | None = None,
) -> BenchmarkReport:
    """Run full benchmark: GWT + baseline for each task."""
    if gwt_mode not in {"tools", "controlled", "hybrid", "attend"}:
        raise ValueError("--gwt-mode must be one of: tools, controlled, hybrid, attend")

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
    embedder = _build_benchmark_embedder(GWTConfig.from_env())

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
        gwt_mode=gwt_mode,
    )

    def run_task_pair(index: int, task: BenchmarkTask) -> tuple[int, TaskResult, TaskResult]:
        gwt_runner = {
            "tools": run_task_gwt,
            "controlled": run_task_gwt_controlled,
            "hybrid": run_task_gwt_hybrid,
            "attend": run_task_gwt_attend,
        }[gwt_mode]
        result_gwt = gwt_runner(client, config.model, task, embedder)
        result_bl = run_task_baseline(client, config.model, task)
        expected_evidence = _expected_evidence_for_task(task)
        for result in (result_gwt, result_bl):
            result.task_metadata = dict(task.metadata)
            result.expected_evidence = list(expected_evidence)
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


def _competition_trace(result: Any) -> dict[str, Any]:
    return {
        "winners": [
            {
                "id": item.id,
                "score": round(result.scores.get(item.id, 0.0), 4),
                "preview": item.content[:160],
            }
            for item in result.winners
        ],
        "evicted": [
            {
                "id": item.id,
                "score": round(result.scores.get(item.id, 0.0), 4),
                "preview": item.content[:160],
            }
            for item in result.evicted
        ],
        "scores": {
            item_id: round(score, 4)
            for item_id, score in sorted(
                result.scores.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        },
    }


def _tool_error(
    tool_name: str,
    message: str,
    trace: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    payload = {"error": message, "tool": tool_name}
    trace["result"] = payload
    trace["error"] = message
    return json.dumps(payload), trace


def _check_answer(predicted: str, expected: str) -> bool:
    """Check if predicted answer matches expected (case-insensitive, substring)."""
    predicted = predicted.lower().strip()
    expected = expected.lower().strip()
    return expected in predicted or predicted in expected


def _average_result_field(results: list[TaskResult], field_name: str) -> float:
    if not results:
        return 0.0
    return sum(float(getattr(result, field_name)) for result in results) / len(results)


def _average_result_metric(results: list[TaskResult], metric_name: str) -> float:
    values = []
    for result in results:
        metrics = _result_evidence_metrics(result)
        if metrics["available"]:
            values.append(metrics[metric_name])
    if not values:
        return 0.0
    return sum(values) / len(values)


def _expected_evidence_for_task(task: BenchmarkTask) -> list[str]:
    raw = task.metadata.get("expected_evidence") or task.metadata.get("chain_facts") or []
    return [str(item) for item in raw]


def _result_evidence_metrics(result: TaskResult) -> dict[str, float | bool]:
    expected = [item for item in result.expected_evidence if item]
    workspace_items = result.workspace_snapshot.get("workspace", {}).get("items", [])
    contents = [
        str(item.get("content", ""))
        for item in workspace_items
        if isinstance(item, dict) and not item.get("empty") and item.get("content")
    ]
    if not expected or not contents:
        return {"precision": 0.0, "recall": 0.0, "available": False}

    matched_expected = [
        evidence
        for evidence in expected
        if any(_evidence_matches(evidence, content) for content in contents)
    ]
    relevant_workspace_items = [
        content
        for content in contents
        if any(_evidence_matches(evidence, content) for evidence in expected)
    ]
    return {
        "precision": len(relevant_workspace_items) / len(contents),
        "recall": len(matched_expected) / len(expected),
        "available": True,
    }


def _evidence_matches(expected: str, content: str) -> bool:
    expected_norm = " ".join(expected.lower().split())
    content_norm = " ".join(content.lower().split())
    return expected_norm in content_norm or content_norm in expected_norm


def _format_controlled_answer(question: str, evidence: EvidencePlan) -> str:
    lines = [
        f"Question: {question}",
        f"Strategy: {evidence.strategy}",
        "Evidence:",
    ]
    lines.extend(f"- {item}" for item in evidence.evidence)
    lines.append(f"ANSWER: {evidence.answer}")
    return "\n".join(lines)


def _build_controlled_evidence(task: BenchmarkTask) -> dict[str, Any]:
    """Compatibility wrapper around benchmark evidence resolvers."""
    return resolve_benchmark_evidence_dict(
        task.question,
        task.context_chunks,
        task.metadata,
    )


def _run_controlled_controller(
    session: GWTSession,
    task: BenchmarkTask,
    trace: list[dict[str, Any]],
) -> AttentionRun:
    controller = AttentionController(
        session.cycle,
        session.ingestion,
        build_benchmark_resolvers(),
        query_k=10,
        admit_query_results=True,
    )
    run = controller.run(
        task.question,
        task.context_chunks,
        task.metadata,
        keywords=extract_question_keywords(task.question),
    )
    for step in run.steps:
        trace.append(
            {
                "phase": step.phase,
                "tool": step.name if step.phase == "controller_tool" else "",
                "result": dict(step.payload),
            }
        )
    return run


def _run_attend_controller(
    session: GWTSession,
    task: BenchmarkTask,
    trace: list[dict[str, Any]],
) -> AttentionRun:
    controller = AttentionController(
        session.cycle,
        session.ingestion,
        [GenericEvidenceResolver(max_queries=6)],
        query_k=10,
        admit_query_results=True,
    )
    run = controller.run(
        task.question,
        task.context_chunks,
        task.metadata,
        keywords=extract_question_keywords(task.question),
        passes=ATTEND_PASSES,
    )
    for step in run.steps:
        trace.append(
            {
                "phase": step.phase,
                "tool": step.name if step.phase == "controller_tool" else "",
                "result": dict(step.payload),
            }
        )
    return run


def _format_hybrid_prompt(question: str, evidence: EvidencePlan | dict[str, Any]) -> str:
    if isinstance(evidence, EvidencePlan):
        evidence_payload = evidence_plan_to_dict(evidence)
    else:
        evidence_payload = evidence
    lines = [
        f"Question: {question}",
        f"GWT strategy: {evidence_payload['strategy']}",
        "Evidence:",
    ]
    if evidence_payload["evidence"]:
        lines.extend(f"- {item}" for item in evidence_payload["evidence"])
    else:
        lines.append("- No matching evidence found.")
    lines.extend(
        [
            f"Controller suggested answer: {evidence_payload['answer']}",
            "Return only the final answer using the required ANSWER format.",
        ]
    )
    return "\n".join(lines)


def _format_attend_prompt(question: str, evidence: EvidencePlan, workspace_text: str) -> str:
    lines = [
        f"Question: {question}",
        f"GWT strategy: {evidence.strategy}",
        f"Controller suggested answer: {evidence.answer or '[none]'}",
        "Controller evidence:",
        "\n".join(f"- {item}" for item in evidence.evidence) or "- No explicit evidence.",
        "Selected workspace evidence:",
        workspace_text or "[empty workspace]",
        "Return only the final answer using the required ANSWER format.",
    ]
    return "\n\n".join(lines)
