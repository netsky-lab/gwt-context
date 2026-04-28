#!/usr/bin/env python
"""Safely clear one Codex gwt-context memory namespace."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

DEFAULT_ROOT = Path.home() / ".gwt-context-codex"


def resolve_target(
    *,
    root: Path = DEFAULT_ROOT,
    project: str | None = None,
    global_namespace: bool = False,
    path: Path | None = None,
) -> Path:
    """Resolve a cleanup target and ensure it stays inside the memory root."""
    selected = sum(value is not None for value in (project, path)) + int(global_namespace)
    if selected != 1:
        raise ValueError("choose exactly one of --project, --global, or --path")

    root = root.expanduser().resolve()
    if project is not None:
        _validate_project_name(project)
        target = root / "projects" / project
    elif global_namespace:
        target = root / "global"
    elif path is not None:
        target = path.expanduser()
    else:
        raise ValueError("cleanup target is required")

    target = target.resolve()
    if target == root:
        raise ValueError("refusing to clear the root memory directory directly")
    if not target.is_relative_to(root):
        raise ValueError(f"target must be inside {root}")
    return target


def clear_namespace(target: Path, *, dry_run: bool = True) -> list[Path]:
    """Return entries that would be cleared, and optionally delete them."""
    target.mkdir(parents=True, exist_ok=True)
    entries = sorted(target.iterdir())
    if dry_run:
        return entries
    for entry in entries:
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    return entries


def _validate_project_name(project: str) -> None:
    if not project or "/" in project or "\\" in project or project in {".", ".."}:
        raise ValueError("project name must be a single safe path segment")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clear one Codex gwt-context memory namespace")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--project")
    parser.add_argument("--global", dest="global_namespace", action="store_true")
    parser.add_argument("--path", type=Path)
    parser.add_argument("--yes", action="store_true", help="Actually delete files")
    args = parser.parse_args()

    try:
        target = resolve_target(
            root=args.root,
            project=args.project,
            global_namespace=args.global_namespace,
            path=args.path,
        )
        entries = clear_namespace(target, dry_run=not args.yes)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    action = "would clear" if not args.yes else "cleared"
    print(f"{action}: {target}")
    if entries:
        for entry in entries:
            print(entry)
    else:
        print("no entries")


if __name__ == "__main__":
    main()
