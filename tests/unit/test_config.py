"""Runtime configuration regressions."""

from pathlib import Path

from gwt_context.infrastructure.config import GWTConfig


def test_gwt_config_loads_documented_environment_overrides(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "custom.db"
    vector_path = tmp_path / "custom-vectors.bin"
    monkeypatch.setenv("GWT_WORKSPACE_CAPACITY", "5")
    monkeypatch.setenv("GWT_BUFFER_SIZE", "25")
    monkeypatch.setenv("GWT_GOAL_MODULATION", "0.4")
    monkeypatch.setenv("GWT_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("GWT_EMBEDDING_MODEL", "hash")
    monkeypatch.setenv("GWT_EMBEDDING_DIM", "32")
    monkeypatch.setenv("GWT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GWT_DB_PATH", str(db_path))
    monkeypatch.setenv("GWT_VECTOR_INDEX_PATH", str(vector_path))
    monkeypatch.setenv("GWT_MAX_BROADCAST_TOKENS", "500")
    monkeypatch.setenv("GWT_MAX_VECTOR_ELEMENTS", "1234")

    config = GWTConfig.from_env()

    assert config.workspace_capacity == 5
    assert config.buffer_size == 25
    assert config.goal_modulation_strength == 0.4
    assert config.embedding_provider == "hash"
    assert config.embedding_model == "hash"
    assert config.embedding_dim == 32
    assert config.data_path == Path(tmp_path / "data")
    assert config.db_path == db_path
    assert config.vector_index_path == vector_path
    assert config.max_broadcast_tokens == 500
    assert config.max_vector_elements == 1234


def test_gwt_config_uses_data_dir_when_paths_are_not_overridden(tmp_path) -> None:
    config = GWTConfig(data_dir=str(tmp_path / "gwt"))

    assert config.db_path == tmp_path / "gwt" / "memory.db"
    assert config.vector_index_path == tmp_path / "gwt" / "vectors.bin"
