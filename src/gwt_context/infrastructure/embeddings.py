"""Embedding providers for vector similarity."""

from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Protocol for embedding text into dense vectors."""

    @property
    def dim(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    """Local embeddings via sentence-transformers. No API key needed.

    Default model: all-MiniLM-L6-v2 (384 dims, fast, good quality).
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model = None  # Lazy init

    def _ensure_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)

    @property
    def dim(self) -> int:
        return 384

    def embed(self, text: str) -> list[float]:
        self._ensure_model()
        return self._model.encode(text).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._ensure_model()
        return self._model.encode(texts).tolist()
