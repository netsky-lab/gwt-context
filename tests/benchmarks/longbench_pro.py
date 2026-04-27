"""LongBench Pro-style information aggregation benchmark for GWT-Context.

Generates tasks requiring aggregation of scattered information:
  - Count occurrences of specific attributes across many records
  - Find items matching multiple criteria
  - Summarize statistics from distributed data points

Inspired by: LongBench v2 / LongBench Pro task types T5-T6.

Usage:
    python -m tests.benchmarks.longbench_pro \
        --api-base http://localhost:8000/v1 \
        --model Qwen/Qwen3-235B-A22B \
        --task-types count filter aggregate \
        --records 30 50 100 \
        --tasks-per-config 5
"""

from __future__ import annotations

import argparse
import hashlib
import random
from pathlib import Path

from tests.benchmarks.config import env_or_default, load_local_env, parse_api_headers
from tests.benchmarks.harness import BenchmarkTask, run_benchmark

# --- Data pools for record generation ---

DEPARTMENTS = [
    "Engineering", "Marketing", "Finance", "Human Resources",
    "Sales", "Research", "Operations", "Legal",
    "Customer Support", "Product", "Design", "Data Science",
]

LOCATIONS = [
    "New York", "San Francisco", "London", "Berlin",
    "Tokyo", "Singapore", "Sydney", "Toronto",
    "Amsterdam", "Dublin", "Stockholm", "Seoul",
]

STATUSES = ["active", "on_leave", "transferred", "probation"]

PROJECT_NAMES = [
    "Atlas", "Beacon", "Catalyst", "Delta", "Echo",
    "Frontier", "Genesis", "Horizon", "Impulse", "Jupiter",
    "Keystone", "Lumen", "Matrix", "Nexus", "Orbit",
    "Prism", "Quantum", "Relay", "Stellar", "Titan",
]

SKILLS = [
    "Python", "Java", "SQL", "Machine Learning", "Cloud Architecture",
    "Data Analysis", "Project Management", "UX Design", "DevOps",
    "Cybersecurity", "Blockchain", "NLP", "Computer Vision", "React",
    "Kubernetes", "Go", "Rust", "TypeScript",
]


def _seed_rng(config_key: str, task_idx: int) -> random.Random:
    h = hashlib.md5(f"{config_key}:{task_idx}".encode()).hexdigest()
    return random.Random(int(h, 16))


def _generate_records(rng: random.Random, n: int) -> list[dict]:
    """Generate employee-like records."""
    records = []
    for i in range(n):
        name = f"Employee-{i+1:03d}"
        record = {
            "name": name,
            "department": rng.choice(DEPARTMENTS),
            "location": rng.choice(LOCATIONS),
            "status": rng.choice(STATUSES),
            "years_experience": rng.randint(1, 25),
            "project": rng.choice(PROJECT_NAMES),
            "skills": rng.sample(SKILLS, rng.randint(1, 4)),
            "performance_score": round(rng.uniform(1.0, 5.0), 1),
            "salary_band": rng.choice(["L3", "L4", "L5", "L6", "L7"]),
        }
        records.append(record)
    return records


def _record_to_text(record: dict) -> str:
    """Convert a record to a natural language passage."""
    return (
        f"{record['name']} works in the {record['department']} department, "
        f"based in {record['location']}. Status: {record['status']}. "
        f"They have {record['years_experience']} years of experience and are "
        f"currently assigned to Project {record['project']}. "
        f"Skills: {', '.join(record['skills'])}. "
        f"Performance score: {record['performance_score']}/5.0. "
        f"Salary band: {record['salary_band']}."
    )


# --- Task generators ---

def _gen_count_task(
    rng: random.Random, records: list[dict], task_idx: int, n_records: int,
) -> BenchmarkTask:
    """Count records matching a criterion."""
    field = rng.choice(["department", "location", "status", "project"])
    values = list({r[field] for r in records})
    target = rng.choice(values)
    count = sum(1 for r in records if r[field] == target)

    chunks = [_record_to_text(r) for r in records]
    rng.shuffle(chunks)

    return BenchmarkTask(
        id=f"lbp_count_{field}_{n_records}rec_{task_idx}",
        question=f"How many employees have {field} = '{target}'? Give just the number.",
        context_chunks=chunks,
        expected_answer=str(count),
        metadata={
            "task_type": "count",
            "field": field,
            "target": target,
            "n_records": n_records,
            "expected_evidence": [
                _record_to_text(record)
                for record in records
                if record[field] == target
            ],
        },
    )


def _gen_filter_task(
    rng: random.Random, records: list[dict], task_idx: int, n_records: int,
) -> BenchmarkTask:
    """Find records matching two criteria."""
    dept = rng.choice(DEPARTMENTS)
    location = rng.choice(LOCATIONS)
    matches = [r for r in records if r["department"] == dept and r["location"] == location]

    chunks = [_record_to_text(r) for r in records]
    rng.shuffle(chunks)

    if matches:
        answer = ", ".join(sorted(r["name"] for r in matches))
    else:
        answer = "none"

    return BenchmarkTask(
        id=f"lbp_filter_{n_records}rec_{task_idx}",
        question=(
            f"List all employees in the {dept} department who are based in {location}. "
            f"Give their names separated by commas, or say 'none' if there are none."
        ),
        context_chunks=chunks,
        expected_answer=answer,
        metadata={
            "task_type": "filter",
            "department": dept,
            "location": location,
            "n_records": n_records,
            "expected_evidence": [_record_to_text(record) for record in matches],
        },
    )


def _gen_aggregate_task(
    rng: random.Random, records: list[dict], task_idx: int, n_records: int,
) -> BenchmarkTask:
    """Aggregate a numeric field."""
    dept = rng.choice(list({r["department"] for r in records}))
    dept_records = [r for r in records if r["department"] == dept]
    avg_exp = round(sum(r["years_experience"] for r in dept_records) / len(dept_records), 1)

    chunks = [_record_to_text(r) for r in records]
    rng.shuffle(chunks)

    return BenchmarkTask(
        id=f"lbp_aggregate_{n_records}rec_{task_idx}",
        question=(
            f"What is the average years of experience for employees in the {dept} department? "
            f"Round to one decimal place."
        ),
        context_chunks=chunks,
        expected_answer=str(avg_exp),
        metadata={
            "task_type": "aggregate",
            "department": dept,
            "n_records": n_records,
            "expected_evidence": [_record_to_text(record) for record in dept_records],
        },
    )


def _gen_top_k_task(
    rng: random.Random, records: list[dict], task_idx: int, n_records: int,
) -> BenchmarkTask:
    """Find top-K records by a numeric field."""
    k = rng.choice([3, 5])
    sorted_records = sorted(records, key=lambda r: r["performance_score"], reverse=True)
    top_k = sorted_records[:k]
    answer = ", ".join(r["name"] for r in top_k)

    chunks = [_record_to_text(r) for r in records]
    rng.shuffle(chunks)

    return BenchmarkTask(
        id=f"lbp_topk_{n_records}rec_{task_idx}",
        question=(
            f"Who are the top {k} employees by performance score? "
            f"List their names in order from highest to lowest, separated by commas."
        ),
        context_chunks=chunks,
        expected_answer=answer,
        metadata={
            "task_type": "top_k",
            "k": k,
            "n_records": n_records,
            "expected_evidence": [_record_to_text(record) for record in top_k],
        },
    )


def _gen_synthesis_task(
    rng: random.Random, records: list[dict], task_idx: int, n_records: int,
) -> BenchmarkTask:
    """Compare two departments and require a compact explanatory synthesis."""
    departments = list({record["department"] for record in records})
    rng.shuffle(departments)
    dept_a, dept_b = departments[:2]
    records_a = [record for record in records if record["department"] == dept_a]
    records_b = [record for record in records if record["department"] == dept_b]
    avg_a = sum(record["years_experience"] for record in records_a) / len(records_a)
    avg_b = sum(record["years_experience"] for record in records_b) / len(records_b)
    winner = dept_a if avg_a >= avg_b else dept_b

    chunks = [_record_to_text(record) for record in records]
    rng.shuffle(chunks)

    return BenchmarkTask(
        id=f"lbp_synthesis_{n_records}rec_{task_idx}",
        question=(
            f"Which department has the higher average years of experience, {dept_a} or "
            f"{dept_b}? Answer with the department name and a brief reason."
        ),
        context_chunks=chunks,
        expected_answer=winner,
        metadata={
            "task_type": "synthesis",
            "department_a": dept_a,
            "department_b": dept_b,
            "average_a": round(avg_a, 1),
            "average_b": round(avg_b, 1),
            "n_records": n_records,
            "expected_evidence": [
                _record_to_text(record) for record in [*records_a, *records_b]
            ],
        },
    )


TASK_GENERATORS = {
    "count": _gen_count_task,
    "filter": _gen_filter_task,
    "aggregate": _gen_aggregate_task,
    "top_k": _gen_top_k_task,
    "synthesis": _gen_synthesis_task,
}


def generate_tasks(
    task_types: list[str] = ["count", "filter", "aggregate"],
    record_counts: list[int] = [30, 50],
    tasks_per_config: int = 5,
) -> list[BenchmarkTask]:
    """Generate LongBench Pro-style aggregation tasks."""
    tasks = []

    for task_type in task_types:
        gen_fn = TASK_GENERATORS[task_type]
        for n_records in record_counts:
            for task_idx in range(tasks_per_config):
                config_key = f"lbp_{task_type}_{n_records}rec"
                rng = _seed_rng(config_key, task_idx)
                records = _generate_records(rng, n_records)
                task = gen_fn(rng, records, task_idx, n_records)
                tasks.append(task)

    return tasks


def main():
    load_local_env()

    parser = argparse.ArgumentParser(
        description="LongBench Pro-style aggregation benchmark for GWT-Context",
    )
    parser.add_argument(
        "--api-base",
        default=env_or_default("BENCHMARK_API_BASE"),
        help="OpenAI-compatible API base URL (default: BENCHMARK_API_BASE from .env/env)",
    )
    parser.add_argument(
        "--model",
        default=env_or_default("BENCHMARK_MODEL"),
        help="Model name (default: BENCHMARK_MODEL from .env/env)",
    )
    parser.add_argument(
        "--api-key",
        default=env_or_default("BENCHMARK_API_KEY", "not-needed"),
        help="API key (default: BENCHMARK_API_KEY from .env/env)",
    )
    parser.add_argument(
        "--api-path",
        default=env_or_default("BENCHMARK_API_PATH", "/v1"),
        help="Relative API path to append to api base (default: BENCHMARK_API_PATH)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=env_or_default("BENCHMARK_TIMEOUT_SECONDS", "30"),
        help="Request timeout seconds (default: BENCHMARK_TIMEOUT_SECONDS)",
    )
    parser.add_argument(
        "--api-headers",
        default=env_or_default("BENCHMARK_API_HEADERS"),
        help="Optional extra headers for API calls (JSON or comma-separated key=value)",
    )
    parser.add_argument(
        "--task-types",
        nargs="+",
        default=["count", "filter", "aggregate"],
        choices=list(TASK_GENERATORS.keys()),
    )
    parser.add_argument(
        "--records", nargs="+", type=int, default=[30, 50], help="Record counts per task",
    )
    parser.add_argument("--tasks-per-config", type=int, default=5, help="Tasks per config")
    parser.add_argument("--max-tasks", type=int, default=None, help="Max total tasks")
    parser.add_argument(
        "--results-dir",
        default=env_or_default("BENCHMARK_RESULTS_DIR", "tests/benchmarks/results"),
        help="Output directory (default: BENCHMARK_RESULTS_DIR)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=int(env_or_default("BENCHMARK_MAX_RETRIES", "2")),
        help="OpenAI client retries (default: BENCHMARK_MAX_RETRIES)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int(env_or_default("BENCHMARK_CONCURRENCY", "1")),
        help="Benchmark task execution concurrency (default: BENCHMARK_CONCURRENCY)",
    )
    parser.add_argument(
        "--gwt-mode",
        choices=["tools", "controlled", "hybrid"],
        default="tools",
        help="GWT execution mode: model-controlled tools or deterministic controller",
    )
    args = parser.parse_args()

    if not args.api_base or not args.model:
        parser.error(
            "provide --api-base and --model, or set "
            "BENCHMARK_API_BASE and BENCHMARK_MODEL in .env",
        )
    if args.api_headers:
        try:
            parse_api_headers(args.api_headers)
        except ValueError as exc:
            parser.error(str(exc))

    tasks = generate_tasks(
        task_types=args.task_types,
        record_counts=args.records,
        tasks_per_config=args.tasks_per_config,
    )
    print(f"Generated {len(tasks)} tasks")
    print(f"  Types: {args.task_types}")
    print(f"  Records: {args.records}")
    print()

    run_benchmark(
        benchmark_name="longbench_pro",
        tasks=tasks,
        api_base=args.api_base,
        model=args.model,
        api_key=args.api_key,
        api_path=args.api_path,
        timeout_seconds=args.timeout,
        api_headers=args.api_headers,
        max_tasks=args.max_tasks,
        results_dir=Path(args.results_dir),
        max_retries=args.max_retries,
        concurrency=args.concurrency,
        gwt_mode=args.gwt_mode,
    )


if __name__ == "__main__":
    main()
