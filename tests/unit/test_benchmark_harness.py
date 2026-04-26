"""Tests for benchmark harness orchestration and persistence."""

import json
from pathlib import Path

import pytest

from tests.benchmarks import harness
from tests.benchmarks.config import BenchmarkConfig
from tests.benchmarks.harness import (
    BenchmarkTask,
    GWTSession,
    TaskResult,
    _build_openai_client,
    run_benchmark,
)


def test_build_openai_client_passes_timeout_and_headers(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(harness, "OpenAI", FakeOpenAI)

    config = BenchmarkConfig(
        api_base="https://api.example.com/v1",
        model="m",
        api_key="k",
        api_path="/v1",
        timeout_seconds=12,
        api_headers={"X-Test": "1"},
        max_retries=7,
    )

    _build_openai_client(config)

    assert captured["api_key"] == "k"
    assert captured["base_url"] == "https://api.example.com/v1"
    assert captured["timeout"] == 12
    assert captured["max_retries"] == 7
    assert captured["default_headers"] == {"X-Test": "1"}


def test_run_benchmark_writes_deterministic_results(monkeypatch, tmp_path: Path) -> None:
    task = BenchmarkTask(
        id="t1",
        question="Q",
        context_chunks=["ctx"],
        expected_answer="ans",
    )

    def fake_build_client(config: BenchmarkConfig):
        return object()

    def fake_task_gwt(*_args: object, **_kwargs: object) -> TaskResult:
        return TaskResult(
            task_id="t1",
            mode="gwt",
            predicted_answer="ans",
            expected_answer="ans",
            correct=True,
            tool_calls=0,
            total_tokens=1,
            latency_seconds=0.0,
        )

    def fake_task_bl(*_args: object, **_kwargs: object) -> TaskResult:
        return TaskResult(
            task_id="t1",
            mode="baseline",
            predicted_answer="ans",
            expected_answer="ans",
            correct=True,
            tool_calls=0,
            total_tokens=2,
            latency_seconds=0.0,
        )

    monkeypatch.setattr(harness, "_build_openai_client", fake_build_client)
    monkeypatch.setattr(harness, "run_task_gwt", fake_task_gwt)
    monkeypatch.setattr(harness, "run_task_baseline", fake_task_bl)
    monkeypatch.setattr(
        harness,
        "SentenceTransformerEmbedder",
        lambda *args, **kwargs: object(),
    )

    report = run_benchmark(
        benchmark_name="ruler_multi_hop",
        tasks=[task],
        api_base="https://api.example.com",
        model="model-x",
        api_key="k",
        api_path="/v1",
        timeout_seconds="15",
        results_dir=tmp_path,
    )

    assert report.run_id.endswith(report.config_hash)
    files = sorted(tmp_path.glob("ruler_multi_hop_model-x_*_*.json"))
    assert len(files) == 1

    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["benchmark_name"] == "ruler_multi_hop"
    assert saved["model"] == "model-x"
    assert saved["api_base"] == "https://api.example.com/v1"
    assert saved["results_dir"] == str(tmp_path)
    assert saved["task_count"] == 1
    assert len(saved["results"]) == 2
    assert saved["gwt_accuracy"] == 1.0
    assert "raw_answer" in saved["results"][0]
    assert "workspace_snapshot" in saved["results"][0]
    assert "trace" in saved["results"][0]


def test_run_benchmark_reuses_and_overrides_config(monkeypatch, tmp_path: Path) -> None:
    task = BenchmarkTask(
        id="t1",
        question="Q",
        context_chunks=["ctx"],
        expected_answer="ans",
    )

    captured: dict[str, object] = {}

    def fake_build_client(config: BenchmarkConfig):
        captured["api_base"] = config.api_base
        captured["model"] = config.model
        return object()

    def fake_task(*_args: object, **_kwargs: object) -> TaskResult:
        return TaskResult(
            task_id="t1",
            mode="gwt",
            predicted_answer="ans",
            expected_answer="ans",
            correct=True,
            tool_calls=0,
            total_tokens=1,
            latency_seconds=0.0,
        )

    monkeypatch.setattr(harness, "_build_openai_client", fake_build_client)
    monkeypatch.setattr(harness, "run_task_gwt", fake_task)
    monkeypatch.setattr(harness, "run_task_baseline", fake_task)
    monkeypatch.setattr(
        harness,
        "SentenceTransformerEmbedder",
        lambda *args, **kwargs: object(),
    )

    base = BenchmarkConfig(
        api_base="https://cfg.example.com/v1",
        model="cfg-model",
        api_key="cfg-key",
        api_path="/v1",
        timeout_seconds=5,
    )

    run_benchmark(
        benchmark_name="ruler_multi_hop",
        tasks=[task],
        config=base,
        api_base="https://cli.example.com",
        api_path="openai",
        timeout_seconds=10,
        model="cli-model",
        results_dir=tmp_path,
    )

    assert captured["api_base"] == "https://cli.example.com/openai"
    assert captured["model"] == "cli-model"


def test_run_benchmark_uses_cli_results_dir(monkeypatch, tmp_path: Path) -> None:
    task = BenchmarkTask(
        id="t1",
        question="Q",
        context_chunks=["ctx"],
        expected_answer="ans",
    )

    captured: dict[str, object] = {}

    def fake_build_client(_config: BenchmarkConfig):
        captured["results_dir"] = _config.results_dir
        return object()

    monkeypatch.setattr(harness, "_build_openai_client", fake_build_client)
    monkeypatch.setattr(harness, "run_task_gwt", lambda *_args, **_kwargs: TaskResult(
        task_id="t1",
        mode="gwt",
        predicted_answer="ans",
        expected_answer="ans",
        correct=True,
        tool_calls=0,
        total_tokens=1,
        latency_seconds=0.0,
    ))
    monkeypatch.setattr(harness, "run_task_baseline", lambda *_args, **_kwargs: TaskResult(
        task_id="t1",
        mode="baseline",
        predicted_answer="ans",
        expected_answer="ans",
        correct=True,
        tool_calls=0,
        total_tokens=2,
        latency_seconds=0.0,
    ))
    monkeypatch.setattr(
        harness,
        "SentenceTransformerEmbedder",
        lambda *args, **kwargs: object(),
    )

    run_benchmark(
        benchmark_name="ruler_multi_hop",
        tasks=[task],
        api_base="https://api.example.com",
        model="model-x",
        api_key="k",
        results_dir=tmp_path,
    )

    assert captured["results_dir"] == str(tmp_path)


def test_run_benchmark_uses_configured_concurrency(monkeypatch, tmp_path: Path) -> None:
    tasks = [
        BenchmarkTask(
            id=f"t{i}",
            question="Q",
            context_chunks=["ctx"],
            expected_answer="ans",
        )
        for i in range(3)
    ]
    captured: dict[str, object] = {}

    class RecordingExecutor:
        def __init__(self, max_workers: int) -> None:
            captured["max_workers"] = max_workers

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def submit(self, fn, *args):  # type: ignore[no-untyped-def]
            class ImmediateFuture:
                def result(self):
                    return fn(*args)

            return ImmediateFuture()

    monkeypatch.setattr(harness, "ThreadPoolExecutor", RecordingExecutor)
    monkeypatch.setattr(harness, "as_completed", lambda futures: list(futures))
    monkeypatch.setattr(harness, "_build_openai_client", lambda _config: object())
    monkeypatch.setattr(
        harness,
        "SentenceTransformerEmbedder",
        lambda *args, **kwargs: object(),
    )

    def fake_gwt(
        _client: object,
        _model: str,
        task: BenchmarkTask,
        _embedder: object,
    ) -> TaskResult:
        return TaskResult(
            task_id=task.id,
            mode="gwt",
            predicted_answer="ans",
            expected_answer="ans",
            correct=True,
            tool_calls=0,
            total_tokens=1,
            latency_seconds=0.0,
        )

    def fake_baseline(_client: object, _model: str, task: BenchmarkTask) -> TaskResult:
        return TaskResult(
            task_id=task.id,
            mode="baseline",
            predicted_answer="ans",
            expected_answer="ans",
            correct=True,
            tool_calls=0,
            total_tokens=1,
            latency_seconds=0.0,
        )

    monkeypatch.setattr(harness, "run_task_gwt", fake_gwt)
    monkeypatch.setattr(harness, "run_task_baseline", fake_baseline)

    report = run_benchmark(
        benchmark_name="ruler_multi_hop",
        tasks=tasks,
        api_base="https://api.example.com",
        model="model-x",
        api_key="k",
        results_dir=tmp_path,
        concurrency=16,
    )

    assert captured["max_workers"] == 16
    assert [result.task_id for result in report.results] == ["t0", "t0", "t1", "t1", "t2", "t2"]


def test_run_benchmark_rejects_misconfigured_api_path() -> None:
    with pytest.raises(ValueError, match="relative"):
        run_benchmark(
            benchmark_name="ruler_multi_hop",
            tasks=[],
            api_base="https://api.example.com",
            model="model-x",
            api_key="k",
            api_path="https://example.com/abs",
        )


def test_gwt_session_returns_structured_tool_errors(monkeypatch) -> None:
    class FakeEmbedder:
        def embed(self, _text: str) -> list[float]:
            return [1.0, 0.0, 0.0, 0.0]

    session = GWTSession(embedder=FakeEmbedder())  # type: ignore[arg-type]
    try:
        result, trace = session.execute_tool_with_trace("gwt_set_goal", {})
    finally:
        session.close()

    assert "missing required argument" in result
    assert trace["error"] == "missing required argument: description"
