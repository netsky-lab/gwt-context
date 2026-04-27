"""Tests for benchmark evidence resolver registry."""

from tests.benchmarks.controlled_rules import resolve_benchmark_evidence


def test_top_k_resolver_extracts_ordered_performance_answer() -> None:
    chunks = [
        (
            "Employee-001 works in the Engineering department, based in New York. "
            "Status: active. They have 4 years of experience and are currently assigned "
            "to Project Atlas. Skills: Python. Performance score: 3.9/5.0. Salary band: L4."
        ),
        (
            "Employee-002 works in the Sales department, based in Berlin. "
            "Status: active. They have 3 years of experience and are currently assigned "
            "to Project Beacon. Skills: SQL. Performance score: 4.8/5.0. Salary band: L3."
        ),
        (
            "Employee-003 works in the Finance department, based in London. "
            "Status: active. They have 5 years of experience and are currently assigned "
            "to Project Delta. Skills: Go. Performance score: 4.2/5.0. Salary band: L5."
        ),
    ]

    plan = resolve_benchmark_evidence(
        "Who are the top 2 employees by performance score? "
        "List their names in order from highest to lowest, separated by commas.",
        chunks,
    )

    assert plan.strategy == "exact_top_k_performance_score"
    assert plan.answer == "Employee-002, Employee-003"
    assert plan.evidence == (
        "Employee-002: performance_score=4.8",
        "Employee-003: performance_score=4.2",
    )


def test_department_comparison_resolver_supports_synthesis_tasks() -> None:
    chunks = [
        (
            "Employee-001 works in the Engineering department, based in New York. "
            "Status: active. They have 10 years of experience and are currently assigned "
            "to Project Atlas. Skills: Python. Performance score: 3.9/5.0. Salary band: L4."
        ),
        (
            "Employee-002 works in the Engineering department, based in Berlin. "
            "Status: active. They have 6 years of experience and are currently assigned "
            "to Project Beacon. Skills: SQL. Performance score: 4.8/5.0. Salary band: L3."
        ),
        (
            "Employee-003 works in the Finance department, based in London. "
            "Status: active. They have 4 years of experience and are currently assigned "
            "to Project Delta. Skills: Go. Performance score: 4.2/5.0. Salary band: L5."
        ),
    ]

    plan = resolve_benchmark_evidence(
        "Which department has the higher average years of experience, Engineering or "
        "Finance? Answer with the department name and a brief reason.",
        chunks,
    )

    assert plan.strategy == "compare_department_average_experience"
    assert plan.answer == "Engineering"
    assert "Engineering: average_years_experience=8.0" in plan.evidence
