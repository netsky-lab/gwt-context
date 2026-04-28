"""Bus on/off benchmark matrix helpers.

The matrix runner is intentionally thin: benchmark entrypoints remain the
source of task generation, while this module standardizes bus on/off commands
and summary comparison over produced JSON artifacts.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.benchmarks.analyze_results import (
    format_markdown,
    load_reports,
    summarize_bus_pairs,
    summarize_report,
)


@dataclass(frozen=True)
class MatrixCommand:
    """One benchmark command in the bus on/off matrix."""

    name: str
    bus_enabled: bool
    command: tuple[str, ...]
    env: dict[str, str]


def build_bus_matrix_commands(
    *,
    python: str = "python",
    max_tasks: int = 0,
) -> tuple[MatrixCommand, ...]:
    """Return the standard bounded bus matrix command set."""
    max_task_args = ("--max-tasks", str(max_tasks)) if max_tasks > 0 else ()
    commands: list[MatrixCommand] = []
    for bus_enabled in (True, False):
        env = {
            "GWT_EMBEDDING_PROVIDER": "hash",
            "GWT_EMBEDDING_MODEL": "hash",
            "GWT_EMBEDDING_DIM": "64",
            "BENCHMARK_CONCURRENCY": "1",
            "BENCHMARK_ATTEND_BROADCAST_BUS": "1" if bus_enabled else "0",
        }
        commands.extend(
            [
                MatrixCommand(
                    name="ruler_advisor",
                    bus_enabled=bus_enabled,
                    env=env,
                    command=(
                        python,
                        "-m",
                        "tests.benchmarks.ruler_multi_hop",
                        "--chain-type",
                        "advisor",
                        "--hops",
                        "2",
                        "--distractors",
                        "3",
                        "10",
                        "--tasks-per-config",
                        "1",
                        *max_task_args,
                        "--gwt-mode",
                        "attend",
                    ),
                ),
                MatrixCommand(
                    name="longbench_core",
                    bus_enabled=bus_enabled,
                    env=env,
                    command=(
                        python,
                        "-m",
                        "tests.benchmarks.longbench_pro",
                        "--task-types",
                        "count",
                        "filter",
                        "aggregate",
                        "top_k",
                        "synthesis",
                        "--records",
                        "12",
                        "--tasks-per-config",
                        "1",
                        *max_task_args,
                        "--gwt-mode",
                        "attend",
                    ),
                ),
            ]
        )
    return tuple(commands)


def run_bus_matrix(commands: tuple[MatrixCommand, ...]) -> None:
    """Execute matrix commands in order."""
    for command in commands:
        env = {**os.environ, **command.env}
        subprocess.run(command.command, check=True, env=env)


def summarize_bus_matrix(paths: list[Path]) -> dict[str, Any]:
    """Summarize bus on/off reports and return markdown plus delta rows."""
    reports = load_reports(paths)
    summaries = [summarize_report(report) for report in reports]
    return {
        "summaries": summaries,
        "bus_pairs": summarize_bus_pairs(summaries),
        "markdown": format_markdown(summaries),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or summarize the bus on/off matrix")
    parser.add_argument("--run", action="store_true", help="Execute the bounded matrix")
    parser.add_argument("--max-tasks", type=int, default=0)
    parser.add_argument("--python", default="python")
    parser.add_argument("--summarize", nargs="*", type=Path, default=[])
    args = parser.parse_args()

    commands = build_bus_matrix_commands(python=args.python, max_tasks=args.max_tasks)
    if args.run:
        run_bus_matrix(commands)
    elif not args.summarize:
        for command in commands:
            env = " ".join(f"{key}={value}" for key, value in sorted(command.env.items()))
            print(f"{env} {' '.join(command.command)}")

    if args.summarize:
        print(summarize_bus_matrix(args.summarize)["markdown"])


if __name__ == "__main__":
    main()
