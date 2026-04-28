"""Tests for the Codex memory cleanup helper."""

from pathlib import Path

import pytest

from scripts.clear_codex_memory import clear_namespace, resolve_target


def test_resolve_project_target_stays_under_root(tmp_path: Path) -> None:
    target = resolve_target(root=tmp_path, project="gwt-context")

    assert target == tmp_path / "projects" / "gwt-context"


def test_resolve_rejects_root_and_external_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="root memory directory"):
        resolve_target(root=tmp_path, path=tmp_path)

    with pytest.raises(ValueError, match="inside"):
        resolve_target(root=tmp_path, path=tmp_path.parent)


def test_clear_namespace_dry_run_preserves_files(tmp_path: Path) -> None:
    target = tmp_path / "projects" / "gwt-context"
    target.mkdir(parents=True)
    db = target / "memory.db"
    db.write_text("memory", encoding="utf-8")

    entries = clear_namespace(target, dry_run=True)

    assert entries == [db]
    assert db.exists()


def test_clear_namespace_deletes_entries_and_keeps_namespace(tmp_path: Path) -> None:
    target = tmp_path / "global"
    nested = target / "nested"
    nested.mkdir(parents=True)
    (nested / "vectors.npy").write_text("vectors", encoding="utf-8")

    entries = clear_namespace(target, dry_run=False)

    assert entries == [nested]
    assert target.exists()
    assert list(target.iterdir()) == []
