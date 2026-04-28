#!/usr/bin/env python
"""Inspect Codex MCP GWT memory namespaces."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_ROOT = Path.home() / ".gwt-context-codex"
DEFAULT_PROJECT = "gwt-context"


@dataclass(frozen=True)
class NamespaceHealth:
    """Filesystem health for one memory namespace."""

    name: str
    path: str
    exists: bool
    entry_count: int
    db_exists: bool
    vector_index_exists: bool


def inspect_namespace(name: str, path: Path) -> NamespaceHealth:
    """Inspect one namespace without modifying it."""
    expanded = path.expanduser()
    entries = list(expanded.iterdir()) if expanded.exists() else []
    return NamespaceHealth(
        name=name,
        path=str(expanded),
        exists=expanded.exists(),
        entry_count=len(entries),
        db_exists=(expanded / "memory.db").exists(),
        vector_index_exists=(expanded / "vectors.bin").exists(),
    )


def inspect_codex_namespaces(
    *,
    root: Path = DEFAULT_ROOT,
    project: str = DEFAULT_PROJECT,
) -> list[NamespaceHealth]:
    """Inspect expected project/global Codex MCP namespaces."""
    root = root.expanduser()
    return [
        inspect_namespace("gwt-context", root / "projects" / project),
        inspect_namespace("gwt-global", root / "global"),
    ]


def run_temp_smoke() -> dict[str, object]:
    """Run stdio MCP smoke against a temporary namespace."""
    with tempfile.TemporaryDirectory() as tmp:
        command = [
            "python",
            "-m",
            "gwt_context.mcp_client_smoke",
            "--compact",
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env={
                **dict(os.environ),
                "GWT_DATA_DIR": tmp,
                "GWT_EMBEDDING_PROVIDER": "hash",
                "GWT_EMBEDDING_MODEL": "hash",
                "GWT_EMBEDDING_DIM": "32",
            },
        )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Codex MCP GWT memory health")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument("--smoke", action="store_true", help="Run temp-dir stdio smoke")
    args = parser.parse_args()

    namespaces = inspect_codex_namespaces(root=args.root, project=args.project)
    payload: dict[str, object] = {
        "namespaces": [asdict(namespace) for namespace in namespaces],
    }
    if args.smoke:
        payload["smoke"] = run_temp_smoke()

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    for namespace in namespaces:
        status = "ok" if namespace.exists else "missing"
        print(f"{namespace.name}: {status} {namespace.path}")
        print(
            "  "
            f"entries={namespace.entry_count} "
            f"db={namespace.db_exists} "
            f"vectors={namespace.vector_index_exists}"
        )
    if args.smoke:
        smoke = payload["smoke"]
        print(f"smoke_returncode={smoke['returncode']}")  # type: ignore[index]


if __name__ == "__main__":
    main()
