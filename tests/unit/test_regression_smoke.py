"""Tests for deterministic benchmark regression smoke."""

from tests.benchmarks.regression_smoke import run_smoke


def test_regression_smoke_passes_generated_tasks() -> None:
    report = run_smoke()

    assert report["task_count"] == 2
    assert report["correct"] == 2
    assert {result["strategy"] for result in report["results"]} == {
        "advisor_chain_resolver",
        "compare_department_average_experience",
    }
