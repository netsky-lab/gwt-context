"""RULER-style multi-hop reasoning benchmark for GWT-Context.

Generates Sequential Needle-In-A-Haystack (S-NIAH) tasks:
  - Scatter linked facts across many distractor passages
  - Require 2-4 hop reasoning to reach the answer
  - Vary context length and needle depth

Based on: RULER: What's the Real Context Size of Your Long-Context LLMs?
(Hsieh et al., 2024)

Usage:
    python -m tests.benchmarks.ruler_multi_hop \
        --api-base http://localhost:8000/v1 \
        --model Qwen/Qwen3-235B-A22B \
        --hops 2 3 4 \
        --distractors 20 50 100 \
        --tasks-per-config 5
"""

from __future__ import annotations

import argparse
import hashlib
import random
from pathlib import Path

from tests.benchmarks.config import env_or_default, load_local_env, parse_api_headers
from tests.benchmarks.harness import BenchmarkTask, run_benchmark

# --- Fact templates for procedural generation ---

ENTITY_POOLS = {
    "scientists": [
        "Marie Curie", "Niels Bohr", "Richard Feynman", "Emmy Noether",
        "Enrico Fermi", "Max Planck", "Werner Heisenberg", "Paul Dirac",
        "Erwin Schrodinger", "Lise Meitner", "Wolfgang Pauli", "John von Neumann",
        "J. Robert Oppenheimer", "Hideki Yukawa", "Abdus Salam",
        "Chen-Ning Yang", "Subrahmanyan Chandrasekhar", "Hans Bethe",
    ],
    "universities": [
        "MIT", "Cambridge", "Oxford", "Caltech", "ETH Zurich",
        "University of Tokyo", "Stanford", "Princeton", "Sorbonne",
        "Gottingen", "Copenhagen", "Leiden", "Berkeley", "Columbia",
        "University of Chicago", "Max Planck Institute", "Imperial College",
    ],
    "cities": [
        "Berlin", "Paris", "Vienna", "Copenhagen", "Rome",
        "Stockholm", "Geneva", "Zurich", "Tokyo", "New York",
        "Chicago", "Cambridge", "Moscow", "Budapest", "Kyoto",
    ],
    "fields": [
        "quantum mechanics", "nuclear physics", "thermodynamics",
        "particle physics", "astrophysics", "condensed matter physics",
        "electrodynamics", "statistical mechanics", "general relativity",
        "quantum field theory", "solid state physics", "plasma physics",
    ],
    "awards": [
        "Nobel Prize in Physics", "Nobel Prize in Chemistry",
        "Max Planck Medal", "Dirac Medal", "Copley Medal",
        "Wolf Prize", "Lorentz Medal", "Enrico Fermi Award",
    ],
}

CHAIN_TEMPLATES = {
    "advisor": {
        "hop_template": "{person_a}'s doctoral advisor was {person_b} at {university}",
        "question_2hop": "Who was the doctoral advisor of the doctoral advisor of {start}?",
        "question_3hop": (
            "Who was the doctoral advisor of the doctoral advisor "
            "of the doctoral advisor of {start}?"
        ),
        "question_4hop": (
            "Who was the doctoral advisor of the doctoral advisor "
            "of the doctoral advisor of the doctoral advisor of {start}?"
        ),
    },
    "workplace": {
        "hop_template": "{person_a} worked with {person_b} at {university}",
        "question_2hop": "Who worked with the person that {start} worked with?",
        "question_3hop": (
            "Who worked with the person who worked with the person "
            "that {start} worked with?"
        ),
        "question_4hop": (
            "Follow four work-with links starting from {start}. "
            "Who is at the end?"
        ),
    },
    "discovery": {
        "hop_template": "{person_a} discovered {field} which was later extended by {person_b}",
        "question_2hop": "Who extended the work of the person who extended {start}'s work?",
        "question_3hop": (
            "Who extended the work of the person who extended the work "
            "of the person who extended {start}'s work?"
        ),
        "question_4hop": (
            "Follow the discovery chain starting from {start} "
            "through 4 extensions. Who is at the end?"
        ),
    },
}

DISTRACTOR_TEMPLATES = [
    "The population of {city} was approximately {num} thousand in the 20th century.",
    "{scientist} received the {award} for contributions to {field}.",
    "The {university} library contains over {num} thousand volumes on {field}.",
    "{city} hosted an international conference on {field} in 19{year}.",
    "Research in {field} at {university} produced {num} publications last decade.",
    "The distance between {city1} and {city2} is approximately {num} kilometers.",
    "{scientist} published a landmark paper on {field} in 19{year}.",
    "The {university} department of {field} was founded in 18{year}.",
    "{scientist} gave a famous lecture series at {university} in 19{year}.",
    "The annual budget for {field} research at {university} exceeded {num} million.",
]


def _seed_rng(config_key: str, task_idx: int) -> random.Random:
    h = hashlib.md5(f"{config_key}:{task_idx}".encode()).hexdigest()
    return random.Random(int(h, 16))


def _generate_chain(rng: random.Random, chain_type: str, n_hops: int) -> tuple[list[str], str, str]:
    """Generate a reasoning chain.

    Returns (chain_facts, question, answer).
    """
    templates = CHAIN_TEMPLATES[chain_type]
    scientists = list(ENTITY_POOLS["scientists"])
    rng.shuffle(scientists)
    universities = list(ENTITY_POOLS["universities"])
    rng.shuffle(universities)

    # Need n_hops + 1 people for n_hops
    people = scientists[: n_hops + 1]
    facts = []
    for i in range(n_hops):
        fact = templates["hop_template"].format(
            person_a=people[i],
            person_b=people[i + 1],
            university=universities[i % len(universities)],
            field=rng.choice(ENTITY_POOLS["fields"]),
        )
        facts.append(fact)

    # Question and answer
    q_key = f"question_{n_hops}hop"
    question = templates.get(q_key, templates["question_2hop"]).format(start=people[0])
    answer = people[-1]

    return facts, question, answer


def _generate_distractors(rng: random.Random, count: int) -> list[str]:
    """Generate distractor passages."""
    distractors = []
    for _ in range(count):
        tmpl = rng.choice(DISTRACTOR_TEMPLATES)
        text = tmpl.format(
            city=rng.choice(ENTITY_POOLS["cities"]),
            city1=rng.choice(ENTITY_POOLS["cities"]),
            city2=rng.choice(ENTITY_POOLS["cities"]),
            scientist=rng.choice(ENTITY_POOLS["scientists"]),
            university=rng.choice(ENTITY_POOLS["universities"]),
            field=rng.choice(ENTITY_POOLS["fields"]),
            award=rng.choice(ENTITY_POOLS["awards"]),
            num=rng.randint(10, 999),
            year=rng.randint(20, 99),
        )
        distractors.append(text)
    return distractors


def generate_tasks(
    n_hops_list: list[int] = [2, 3],
    distractor_counts: list[int] = [20, 50],
    tasks_per_config: int = 5,
    chain_type: str = "advisor",
) -> list[BenchmarkTask]:
    """Generate RULER-style multi-hop tasks."""
    tasks = []

    for n_hops in n_hops_list:
        for n_distractors in distractor_counts:
            for task_idx in range(tasks_per_config):
                config_key = f"ruler_{chain_type}_{n_hops}hop_{n_distractors}dist"
                rng = _seed_rng(config_key, task_idx)

                chain_facts, question, answer = _generate_chain(rng, chain_type, n_hops)
                distractors = _generate_distractors(rng, n_distractors)

                # Scatter chain facts among distractors
                all_chunks = list(distractors)
                for i, fact in enumerate(chain_facts):
                    # Spread across the context
                    pos = int((i + 1) / (n_hops + 1) * len(all_chunks))
                    all_chunks.insert(pos, fact)

                task = BenchmarkTask(
                    id=f"{config_key}_{task_idx}",
                    question=question,
                    context_chunks=all_chunks,
                    expected_answer=answer,
                    metadata={
                        "n_hops": n_hops,
                        "n_distractors": n_distractors,
                        "chain_type": chain_type,
                        "chain_facts": chain_facts,
                        "expected_evidence": chain_facts,
                    },
                )
                tasks.append(task)

    return tasks


def main():
    load_local_env()

    parser = argparse.ArgumentParser(
        description="RULER multi-hop benchmark for GWT-Context",
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
        "--hops", nargs="+", type=int, default=[2, 3], help="Number of hops to test",
    )
    parser.add_argument(
        "--distractors", nargs="+", type=int, default=[20, 50], help="Distractor counts",
    )
    parser.add_argument(
        "--tasks-per-config",
        type=int,
        default=5,
        help="Tasks per (hops, distractors) config",
    )
    parser.add_argument("--chain-type", default="advisor", choices=list(CHAIN_TEMPLATES.keys()))
    parser.add_argument("--max-tasks", type=int, default=None, help="Max total tasks to run")
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
        n_hops_list=args.hops,
        distractor_counts=args.distractors,
        tasks_per_config=args.tasks_per_config,
        chain_type=args.chain_type,
    )
    print(f"Generated {len(tasks)} tasks")
    print(f"  Hops: {args.hops}")
    print(f"  Distractors: {args.distractors}")
    print(f"  Chain type: {args.chain_type}")
    print()

    run_benchmark(
        benchmark_name="ruler_multi_hop",
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
