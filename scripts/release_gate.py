#!/usr/bin/env python
"""Run the local release gate used before tagging/publishing."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class GateCommand:
    """One release gate command."""

    name: str
    command: tuple[str, ...]
    env: dict[str, str] | None = None


def build_gate_commands() -> tuple[GateCommand, ...]:
    """Return the command sequence for a full release gate."""
    hash_env = {
        "GWT_EMBEDDING_PROVIDER": "hash",
        "GWT_EMBEDDING_MODEL": "hash",
    }
    return (
        GateCommand("pytest", ("pytest", "-q")),
        GateCommand("ruff", ("ruff", "check", ".")),
        GateCommand("mypy", ("mypy", "src")),
        GateCommand("npm", ("npm", "test", "--", "--quiet")),
        GateCommand("local-smoke", ("python", "-m", "gwt_context.smoke"), hash_env),
        GateCommand(
            "stdio-mcp-smoke",
            ("python", "-m", "gwt_context.mcp_client_smoke", "--compact"),
            hash_env,
        ),
        GateCommand("real-usage-loop", ("python", "examples/real_usage_loop.py")),
        GateCommand(
            "external-subscriber-poc",
            ("python", "examples/external_subscriber_poc.py"),
        ),
        GateCommand("build", ("python", "-m", "build")),
    )


def run_gate(*, skip_slow: bool = False, boundary_only: bool = False) -> None:
    """Run release commands and static boundary checks."""
    commands = build_gate_commands()
    if boundary_only:
        run_boundary_checks()
        return
    if skip_slow:
        commands = tuple(
            command for command in commands if command.name not in {"pytest", "npm", "build"}
        )
    for command in commands:
        _run(command)
    run_boundary_checks()


def run_boundary_checks() -> None:
    """Fail if known architecture, artifact, or secret boundaries regress."""
    _check_no_matches(
        "mcp-private-coupling",
        (
            "rg",
            "-n",
            (
                r"cycle\.(workspace|buffer|goal_manager)|"
                r"_cycle\.(workspace|buffer|goal_manager)|"
                r"from gwt_context\.infrastructure|tests\.benchmarks"
            ),
            "src/gwt_context/mcp",
            "src/gwt_context/application",
        ),
    )
    _check_no_matches(
        "application-forbidden-imports",
        (
            "rg",
            "-n",
            (
                r"from gwt_context\.infrastructure|"
                r"import gwt_context\.infrastructure|"
                r"tests\.benchmarks"
            ),
            "src/gwt_context/application",
            "src/gwt_context/domain",
        ),
    )
    tracked = subprocess.run(
        ("git", "ls-files"),
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()
    artifact_pattern = re.compile(
        r"(tests/benchmarks/(results|reports)|tests/benchmarks/.*\.log|"
        r"\.env$|supervisor|\.benchmarks|\.worktrees|dist/)"
    )
    leaked_artifacts = [path for path in tracked if artifact_pattern.search(path)]
    if leaked_artifacts:
        raise RuntimeError(f"tracked generated artifacts: {leaked_artifacts}")
    _check_no_secret_needles()


def _run(command: GateCommand) -> None:
    print(f"==> {command.name}: {' '.join(command.command)}", flush=True)
    env = dict(os.environ)
    if command.env:
        env.update(command.env)
    subprocess.run(command.command, cwd=REPO_ROOT, env=env, check=True)


def _check_no_matches(name: str, command: tuple[str, ...]) -> None:
    print(f"==> boundary: {name}", flush=True)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode == 0:
        raise RuntimeError(f"{name} matched forbidden content:\n{result.stdout}")
    if result.returncode not in {0, 1}:
        raise RuntimeError(f"{name} check failed:\n{result.stdout}")


def _check_no_secret_needles() -> None:
    print("==> boundary: runpod-url", flush=True)
    needles = ("proxy." + "runpod.net", "lsjdwbaa4" + "qmjki")
    listed = subprocess.run(
        ("git", "ls-files", "--cached", "--others", "--exclude-standard"),
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()
    ignored_prefixes = (
        "research/",
        "dist/",
        "tests/benchmarks/results/",
        ".benchmarks/",
        ".supervisor/",
    )
    matches: list[str] = []
    for raw_path in listed:
        if raw_path == ".env" or raw_path.startswith(ignored_prefixes):
            continue
        path = REPO_ROOT / raw_path
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for needle in needles:
            if needle in text:
                matches.append(raw_path)
                break
    if matches:
        raise RuntimeError(f"secret endpoint material found in tracked files: {matches}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local release gates")
    parser.add_argument(
        "--skip-slow",
        action="store_true",
        help="Skip pytest/npm/build while keeping lint, smoke, and boundary checks",
    )
    parser.add_argument(
        "--boundary-only",
        action="store_true",
        help="Only run architecture, artifact, and secret boundary checks",
    )
    args = parser.parse_args()
    try:
        run_gate(skip_slow=args.skip_slow, boundary_only=args.boundary_only)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"release gate failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print("release gate passed")


if __name__ == "__main__":
    main()
