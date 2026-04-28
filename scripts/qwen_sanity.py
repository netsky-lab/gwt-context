#!/usr/bin/env python
"""Print or run the bounded Qwen/OpenAI-compatible sanity matrix."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    from tests.benchmarks.bus_matrix import build_bus_matrix_commands, run_bus_matrix
    from tests.benchmarks.config import load_local_env

    parser = argparse.ArgumentParser(description="Run bounded Qwen sanity checks")
    parser.add_argument("--run", action="store_true", help="Execute the matrix")
    parser.add_argument("--max-tasks", type=int, default=1)
    parser.add_argument("--python", default="python")
    parser.add_argument(
        "--results-dir",
        default=".benchmarks/qwen-sanity",
        help="Ignored local output directory for benchmark JSON",
    )
    args = parser.parse_args()

    load_local_env()
    _require_env("BENCHMARK_API_BASE")
    _require_env("BENCHMARK_MODEL")

    os.environ["BENCHMARK_RESULTS_DIR"] = args.results_dir
    os.environ.setdefault("GWT_EMBEDDING_PROVIDER", "hash")
    os.environ.setdefault("GWT_EMBEDDING_MODEL", "hash")
    os.environ.setdefault("GWT_EMBEDDING_DIM", "64")
    Path(args.results_dir).mkdir(parents=True, exist_ok=True)

    commands = build_bus_matrix_commands(python=args.python, max_tasks=args.max_tasks)
    if args.run:
        run_bus_matrix(commands)
        print(f"wrote benchmark reports under {args.results_dir}")
        return
    for command in commands:
        env = " ".join(f"{key}={value}" for key, value in sorted(command.env.items()))
        print(f"{env} {' '.join(command.command)}")


def _require_env(name: str) -> None:
    if not os.environ.get(name, "").strip():
        raise SystemExit(f"{name} is required; set it in .env or the environment")


if __name__ == "__main__":
    main()
