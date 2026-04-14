"""Helpers for loading local benchmark configuration."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = REPO_ROOT / ".env"


def load_local_env(env_path: Path = DEFAULT_ENV_PATH) -> None:
    """Load simple KEY=VALUE pairs from a local .env file."""
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def env_or_default(env_name: str, default: str | None = None) -> str | None:
    """Return an environment value if present, otherwise a default."""
    return os.environ.get(env_name, default)
