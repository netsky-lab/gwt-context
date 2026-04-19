"""Tests for benchmark configuration loading/parsing."""

import pytest

from tests.benchmarks.config import (
    BenchmarkConfig,
    canonicalize_api_endpoint,
    load_benchmark_config,
    parse_api_headers,
)


def test_load_benchmark_config_precedence_and_canonicalization(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BENCHMARK_API_BASE", "https://env.example.com")
    monkeypatch.setenv("BENCHMARK_MODEL", "env-model")
    monkeypatch.setenv("BENCHMARK_API_KEY", "env-key")
    monkeypatch.setenv("BENCHMARK_API_PATH", "/v1")
    monkeypatch.setenv("BENCHMARK_TIMEOUT_SECONDS", "42")

    config = load_benchmark_config(
        api_base="https://cli.example.com/api",
        model=None,
        api_path="openai",
        max_retries=3,
        concurrency=4,
        results_dir=tmp_path,
        api_headers='{"X-From":"cli"}',
    )

    assert isinstance(config, BenchmarkConfig)
    assert config.api_base == "https://cli.example.com/api/openai"
    assert config.model == "env-model"
    assert config.api_key == "env-key"
    assert config.timeout_seconds == 42.0
    assert config.max_retries == 3
    assert config.concurrency == 4
    assert config.results_dir == str(tmp_path)
    assert config.api_headers == {"X-From": "cli"}


def test_load_benchmark_config_requires_base_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BENCHMARK_API_BASE", raising=False)
    monkeypatch.delenv("BENCHMARK_MODEL", raising=False)

    with pytest.raises(ValueError, match="BENCHMARK_API_BASE is required"):
        load_benchmark_config(api_base=None, model=None, api_key="k")

    monkeypatch.setenv("BENCHMARK_API_BASE", "https://api.example.com")
    with pytest.raises(ValueError, match="BENCHMARK_MODEL is required"):
        load_benchmark_config(api_base=None, model=None, api_key="k")


def test_parse_api_headers_accepts_json_and_csv() -> None:
    assert parse_api_headers('{"X-1":"a", "Y":"b"}') == {"X-1": "a", "Y": "b"}
    assert parse_api_headers("x=1,y=two, z=3") == {"x": "1", "y": "two", "z": "3"}
    assert parse_api_headers("  ") == {}


def test_parse_api_headers_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="JSON"):
        parse_api_headers('{invalid')

    with pytest.raises(ValueError, match="key=value"):
        parse_api_headers("bad-header")


def test_canonicalize_api_endpoint_is_deterministic() -> None:
    assert (
        canonicalize_api_endpoint("https://api.example.com/v1", "/v1")
        == "https://api.example.com/v1"
    )
    assert (
        canonicalize_api_endpoint("https://api.example.com/base/", "path")
        == "https://api.example.com/base/path"
    )
    assert canonicalize_api_endpoint("https://api.example.com", "") == "https://api.example.com"


def test_canonicalize_api_endpoint_rejects_absolute_path() -> None:
    with pytest.raises(ValueError, match="absolute URL"):
        canonicalize_api_endpoint("https://api.example.com", "https://evil/path")


def test_canonicalize_api_endpoint_rejects_missing_base() -> None:
    with pytest.raises(ValueError, match="required"):
        canonicalize_api_endpoint("  ", "/v1")
