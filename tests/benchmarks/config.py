"""Helpers for loading local benchmark configuration."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = REPO_ROOT / ".env"

DEFAULT_BENCHMARK_RESULTS_DIR = "tests/benchmarks/results"
DEFAULT_BENCHMARK_TIMEOUT_SECONDS = 30.0
DEFAULT_BENCHMARK_MAX_RETRIES = 2
DEFAULT_BENCHMARK_CONCURRENCY = 1
DEFAULT_BENCHMARK_API_PATH = "/v1"


@dataclass
class BenchmarkConfig:
    """Benchmark runtime configuration loaded from CLI args + environment."""

    api_base: str
    model: str
    api_key: str = "not-needed"
    api_path: str = "/v1"
    timeout_seconds: float = DEFAULT_BENCHMARK_TIMEOUT_SECONDS
    api_headers: dict[str, str] = field(default_factory=dict)
    results_dir: str = DEFAULT_BENCHMARK_RESULTS_DIR
    max_retries: int = DEFAULT_BENCHMARK_MAX_RETRIES
    concurrency: int = DEFAULT_BENCHMARK_CONCURRENCY


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

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def env_or_default(env_name: str, default: str | None = None) -> str | None:
    """Return an environment value if present, otherwise a default."""
    return os.environ.get(env_name, default)


def _parse_positive_float(raw: str | float | int | None, *, name: str) -> float:
    if raw is None:
        if name == "BENCHMARK_TIMEOUT_SECONDS":
            return DEFAULT_BENCHMARK_TIMEOUT_SECONDS
        raise ValueError(f"{name} is required")

    value = float(raw)
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return value


def _parse_positive_int(raw: str | int | None, *, name: str) -> int:
    if raw is None:
        if name == "BENCHMARK_MAX_RETRIES":
            return DEFAULT_BENCHMARK_MAX_RETRIES
        if name == "BENCHMARK_CONCURRENCY":
            return DEFAULT_BENCHMARK_CONCURRENCY
        return 1

    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return value


def parse_api_headers(raw: str | None) -> dict[str, str]:
    """Parse optional API headers.

    Supports JSON objects and simple comma-separated key=value pairs.
    """

    if raw is None:
        return {}

    raw = raw.strip()
    if not raw:
        return {}

    if raw.startswith("{") and raw.endswith("}"):
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON for BENCHMARK_API_HEADERS: {exc}") from exc

        if not isinstance(loaded, dict):
            raise ValueError("BENCHMARK_API_HEADERS JSON must be an object")

        headers: dict[str, str] = {}
        for key, value in loaded.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError(
                    "BENCHMARK_API_HEADERS values must be string key/value pairs",
                )
            headers[key.strip()] = value.strip()
        return headers

    parts = [entry.strip() for entry in raw.split(",") if entry.strip()]
    headers: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            raise ValueError(
                "BENCHMARK_API_HEADERS must be JSON or comma-separated key=value pairs",
            )
        key, value = [item.strip() for item in part.split("=", 1)]
        if not key:
            raise ValueError("BENCHMARK_API_HEADERS contains an empty key")
        headers[key] = value
    return headers


def canonicalize_api_endpoint(api_base: str, api_path: str | None) -> str:
    """Combine base URL and optional path deterministically."""
    base = api_base.strip().rstrip("/")
    if not base:
        raise ValueError("BENCHMARK_API_BASE is required")

    if not api_path:
        return base

    path = api_path.strip()
    if not path:
        return base

    if path.startswith("http://") or path.startswith("https://"):
        raise ValueError("BENCHMARK_API_PATH must be a relative path, not an absolute URL")

    if not path.startswith("/"):
        path = f"/{path}"
    path = path.rstrip("/")

    parsed = urlsplit(base)
    if not parsed.scheme:
        raise ValueError(f"api base must be absolute URL-like: {api_base!r}")

    base_path = parsed.path.rstrip("/")
    if base_path.strip("/") == path.strip("/"):
        combined_path = base_path or "/"
    else:
        combined_path = f"{base_path}{path}"

    if not combined_path:
        combined_path = "/"

    return urlunsplit((parsed.scheme, parsed.netloc, combined_path, "", ""))


def load_benchmark_config(
    *,
    api_base: str | None,
    model: str | None,
    api_key: str | None = None,
    api_path: str | None = None,
    timeout_seconds: str | float | int | None = None,
    api_headers: str | None = None,
    results_dir: str | Path | None = None,
    max_retries: str | int | None = None,
    concurrency: str | int | None = None,
) -> BenchmarkConfig:
    """Resolve benchmark configuration with deterministic precedence and validation."""
    resolved_api_base = (api_base or env_or_default("BENCHMARK_API_BASE", "")).strip()
    if not resolved_api_base:
        raise ValueError("BENCHMARK_API_BASE is required; set --api-base or BENCHMARK_API_BASE")

    resolved_model = (model or env_or_default("BENCHMARK_MODEL", "")).strip()
    if not resolved_model:
        raise ValueError("BENCHMARK_MODEL is required; set --model or BENCHMARK_MODEL")

    resolved_api_key = (
        api_key or env_or_default("BENCHMARK_API_KEY", "not-needed")
    ).strip()
    if not resolved_api_key:
        raise ValueError("BENCHMARK_API_KEY cannot be empty")

    resolved_api_path = (
        api_path if api_path is not None else env_or_default("BENCHMARK_API_PATH", "/v1")
    ).strip()
    if not resolved_api_path:
        resolved_api_path = DEFAULT_BENCHMARK_API_PATH
    resolved_timeout = _parse_positive_float(
        timeout_seconds
        if timeout_seconds is not None
        else env_or_default(
            "BENCHMARK_TIMEOUT_SECONDS",
            str(DEFAULT_BENCHMARK_TIMEOUT_SECONDS),
        ),
        name="BENCHMARK_TIMEOUT_SECONDS",
    )
    resolved_max_retries = _parse_positive_int(
        max_retries
        if max_retries is not None
        else env_or_default("BENCHMARK_MAX_RETRIES", str(DEFAULT_BENCHMARK_MAX_RETRIES)),
        name="BENCHMARK_MAX_RETRIES",
    )
    resolved_concurrency = _parse_positive_int(
        concurrency
        if concurrency is not None
        else env_or_default(
            "BENCHMARK_CONCURRENCY",
            str(DEFAULT_BENCHMARK_CONCURRENCY),
        ),
        name="BENCHMARK_CONCURRENCY",
    )

    if resolved_max_retries > 10:
        raise ValueError("BENCHMARK_MAX_RETRIES must be <= 10")

    headers_raw = (
        api_headers
        if api_headers is not None
        else env_or_default("BENCHMARK_API_HEADERS")
    )
    headers = parse_api_headers(headers_raw)

    resolved_results_dir = str(
        results_dir
        or env_or_default("BENCHMARK_RESULTS_DIR", DEFAULT_BENCHMARK_RESULTS_DIR)
    )

    canonical_base = canonicalize_api_endpoint(resolved_api_base, resolved_api_path)
    canonical_base = re.sub(r"\s+", "", canonical_base)
    if not canonical_base:
        raise ValueError("BENCHMARK_API_BASE is required")

    return BenchmarkConfig(
        api_base=canonical_base,
        model=resolved_model,
        api_key=resolved_api_key,
        api_path=resolved_api_path,
        timeout_seconds=resolved_timeout,
        api_headers=headers,
        results_dir=resolved_results_dir,
        max_retries=resolved_max_retries,
        concurrency=resolved_concurrency,
    )
