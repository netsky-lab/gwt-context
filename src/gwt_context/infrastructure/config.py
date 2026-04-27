"""Configuration for GWT-Context server."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GWTConfig:
    """All configurable parameters for the GWT system.

    Values can be overridden via environment variables prefixed with GWT_.
    Example: GWT_WORKSPACE_CAPACITY=5
    """

    # Workspace
    workspace_capacity: int = 7
    max_broadcast_tokens: int = 4000

    # Pre-conscious buffer
    buffer_size: int = 50

    # Competition
    goal_modulation_strength: float = 0.3
    min_activation: float = 0.2
    specialist_weights: dict[str, float] = field(default_factory=lambda: {
        "relevance": 0.35,
        "recency": 0.20,
        "frequency": 0.10,
        "linkage": 0.20,
        "novelty": 0.15,
    })

    # Embeddings
    embedding_provider: str = "sentence-transformer"
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Storage
    data_dir: str = "~/.gwt-context"
    db_name: str = "memory.db"
    vector_index_name: str = "vectors.bin"
    db_path_override: str | None = None
    vector_index_path_override: str | None = None
    max_vector_elements: int = 100_000

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).expanduser()

    @property
    def db_path(self) -> Path:
        if self.db_path_override:
            return Path(self.db_path_override).expanduser()
        return self.data_path / self.db_name

    @property
    def vector_index_path(self) -> Path:
        if self.vector_index_path_override:
            return Path(self.vector_index_path_override).expanduser()
        return self.data_path / self.vector_index_name

    def ensure_data_dir(self) -> None:
        """Create data directory if it doesn't exist."""
        self.data_path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> GWTConfig:
        """Load config with environment variable overrides."""
        config = cls()
        env_map = {
            "GWT_WORKSPACE_CAPACITY": ("workspace_capacity", int),
            "GWT_BUFFER_SIZE": ("buffer_size", int),
            "GWT_GOAL_MODULATION": ("goal_modulation_strength", float),
            "GWT_MIN_ACTIVATION": ("min_activation", float),
            "GWT_EMBEDDING_PROVIDER": ("embedding_provider", str),
            "GWT_EMBEDDING_MODEL": ("embedding_model", str),
            "GWT_EMBEDDING_DIM": ("embedding_dim", int),
            "GWT_DATA_DIR": ("data_dir", str),
            "GWT_DB_PATH": ("db_path_override", str),
            "GWT_VECTOR_INDEX_PATH": ("vector_index_path_override", str),
            "GWT_MAX_BROADCAST_TOKENS": ("max_broadcast_tokens", int),
            "GWT_MAX_VECTOR_ELEMENTS": ("max_vector_elements", int),
        }
        for env_key, (attr, type_fn) in env_map.items():
            val = os.environ.get(env_key)
            if val is not None:
                setattr(config, attr, type_fn(val))
        return config
