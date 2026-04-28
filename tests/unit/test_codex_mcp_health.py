"""Tests for Codex MCP health helper."""

from pathlib import Path

from scripts.codex_mcp_health import inspect_codex_namespaces, inspect_namespace


def test_inspect_namespace_reports_db_and_vector_files(tmp_path: Path) -> None:
    namespace = tmp_path / "project"
    namespace.mkdir()
    (namespace / "memory.db").write_text("", encoding="utf-8")
    (namespace / "vectors.bin").write_bytes(b"")

    health = inspect_namespace("project", namespace)

    assert health.exists is True
    assert health.entry_count == 2
    assert health.db_exists is True
    assert health.vector_index_exists is True


def test_inspect_codex_namespaces_uses_project_and_global_layout(tmp_path: Path) -> None:
    (tmp_path / "projects" / "demo").mkdir(parents=True)
    (tmp_path / "global").mkdir()

    health = inspect_codex_namespaces(root=tmp_path, project="demo")

    assert [item.name for item in health] == ["gwt-context", "gwt-global"]
    assert health[0].path == str(tmp_path / "projects" / "demo")
    assert health[1].path == str(tmp_path / "global")
