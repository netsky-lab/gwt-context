"""Tests for Codex MCP bootstrap helper."""

from pathlib import Path

from scripts.codex_mcp_bootstrap import codex_mcp_commands, ensure_namespace_dirs


def test_codex_mcp_commands_use_split_project_and_global_namespaces(tmp_path: Path) -> None:
    commands = codex_mcp_commands(root=tmp_path, project="gwt-context", embedding_dim=64)

    rendered = [" ".join(command) for command in commands]
    assert "gwt-context" in commands[0]
    assert "gwt-global" in commands[1]
    assert f"GWT_DATA_DIR={tmp_path / 'projects' / 'gwt-context'}" in commands[0]
    assert f"GWT_DATA_DIR={tmp_path / 'global'}" in commands[1]
    assert all("GWT_EMBEDDING_PROVIDER=hash" in command for command in commands)
    assert any("GWT_EMBEDDING_DIM=64" in command for command in commands[0])
    assert " ".join(rendered)


def test_ensure_namespace_dirs_creates_expected_layout(tmp_path: Path) -> None:
    ensure_namespace_dirs(root=tmp_path, project="demo")

    assert (tmp_path / "projects" / "demo").is_dir()
    assert (tmp_path / "global").is_dir()
