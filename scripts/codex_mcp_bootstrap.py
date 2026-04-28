#!/usr/bin/env python
"""Print or apply Codex MCP registrations for project/global GWT memory."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

DEFAULT_ROOT = Path.home() / ".gwt-context-codex"
DEFAULT_PROJECT = "gwt-context"


def codex_mcp_commands(
    *,
    root: Path = DEFAULT_ROOT,
    project: str = DEFAULT_PROJECT,
    embedding_dim: int = 32,
) -> list[list[str]]:
    """Return Codex CLI commands for project and global MCP servers."""
    root = root.expanduser()
    project_dir = root / "projects" / project
    global_dir = root / "global"
    base_env = [
        "--env",
        "GWT_EMBEDDING_PROVIDER=hash",
        "--env",
        "GWT_EMBEDDING_MODEL=hash",
        "--env",
        f"GWT_EMBEDDING_DIM={embedding_dim}",
    ]
    return [
        [
            "codex",
            "mcp",
            "add",
            "gwt-context",
            *base_env,
            "--env",
            f"GWT_DATA_DIR={project_dir}",
            "--",
            "python",
            "-m",
            "gwt_context",
        ],
        [
            "codex",
            "mcp",
            "add",
            "gwt-global",
            *base_env,
            "--env",
            f"GWT_DATA_DIR={global_dir}",
            "--",
            "python",
            "-m",
            "gwt_context",
        ],
    ]


def ensure_namespace_dirs(*, root: Path = DEFAULT_ROOT, project: str = DEFAULT_PROJECT) -> None:
    """Create expected project/global namespace directories."""
    root = root.expanduser()
    (root / "projects" / project).mkdir(parents=True, exist_ok=True)
    (root / "global").mkdir(parents=True, exist_ok=True)


def shell_command(argv: list[str]) -> str:
    """Render a command for copy/paste logs."""
    return " ".join(_quote(part) for part in argv)


def _quote(value: str) -> str:
    if not value or any(char.isspace() for char in value):
        return "'" + value.replace("'", "'\"'\"'") + "'"
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap Codex MCP GWT servers")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--embedding-dim", type=int, default=32)
    parser.add_argument("--apply", action="store_true", help="Run codex mcp add commands")
    args = parser.parse_args()

    ensure_namespace_dirs(root=args.root, project=args.project)
    commands = codex_mcp_commands(
        root=args.root,
        project=args.project,
        embedding_dim=args.embedding_dim,
    )
    for command in commands:
        print(shell_command(command))
        if args.apply:
            subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
