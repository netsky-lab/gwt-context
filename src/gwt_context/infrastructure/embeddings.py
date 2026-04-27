"""Embedding providers for vector similarity."""

from __future__ import annotations

import hashlib
from threading import Lock
from typing import Any, Protocol


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
        self._model_lock = Lock()

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        with self._model_lock:
            if self._model is not None:
                return
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
        return _as_float_list(embedding)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._ensure_model()
        model = self._model
        assert model is not None
        embeddings = model.encode(texts)
        return _as_float_matrix(embeddings)


class HashEmbeddingEmbedder:
    """Deterministic local embeddings for offline smoke and tests.

    This provider is intentionally simple. It avoids model downloads and network
    access while preserving vector-search behavior for local readiness checks.
    """

    def __init__(self, dim: int = 384) -> None:
        if dim <= 0:
            raise ValueError("embedding dimension must be greater than 0")
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        tokens = [token for token in text.lower().split() if token]
        for token in tokens or [text]:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self._dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        return vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


def _as_float_list(values: Any) -> list[float]:
    if hasattr(values, "tolist"):
        values = values.tolist()
    return [float(value) for value in values]


def _as_float_matrix(values: Any) -> list[list[float]]:
    if hasattr(values, "tolist"):
        values = values.tolist()
    return [_as_float_list(row) for row in values]
