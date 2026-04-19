"""Embedding providers for vector similarity."""

from __future__ import annotations

from typing import Any, Protocol, cast


class EmbeddingBackendProtocol(Protocol):
    """Minimal interface for an embedding model."""

    def encode(self, *args: Any, **kwargs: Any) -> Any:
        ...


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
        self._model: EmbeddingBackendProtocol | None = None

    def _ensure_model(self) -> None:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)

    @property
    def dim(self) -> int:
        return 384

    def embed(self, text: str) -> list[float]:
        self._ensure_model()
        model = self._model
        assert model is not None
        embedding = model.encode(text)
        return cast(list[float], embedding)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._ensure_model()
        model = self._model
        assert model is not None
        embeddings = model.encode(texts)
        return cast(list[list[float]], embeddings)
