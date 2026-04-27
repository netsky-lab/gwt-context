"""Embedding provider contract regressions."""

import numpy as np
import pytest

from gwt_context.infrastructure.embeddings import HashEmbeddingEmbedder, SentenceTransformerEmbedder


class ArrayBackend:
    """Minimal backend returning numpy arrays like sentence-transformers."""

    def encode(self, text_or_texts: object) -> object:
        if isinstance(text_or_texts, list):
            return np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32)
        return np.array([1, 2, 3], dtype=np.float32)


def test_sentence_transformer_embedder_returns_python_lists() -> None:
    embedder = SentenceTransformerEmbedder()
    embedder._model = ArrayBackend()

    assert embedder.embed("hello") == [1.0, 2.0, 3.0]
    assert embedder.embed_batch(["hello", "world"]) == [
        [1.0, 2.0, 3.0],
        [4.0, 5.0, 6.0],
    ]


def test_sentence_transformer_embedder_lazy_load_is_thread_safe(monkeypatch) -> None:
    loads = 0

    class Backend:
        def encode(self, _text: object) -> object:
            return [1, 2, 3]

    class FakeSentenceTransformer:
        def __init__(self, _model_name: str) -> None:
            nonlocal loads
            loads += 1

        def encode(self, _text: object) -> object:
            return Backend().encode(_text)

    def fake_import(_name: str, *_args: object, **_kwargs: object) -> object:
        if _name == "sentence_transformers":
            class Module:
                SentenceTransformer = FakeSentenceTransformer

            return Module()
        raise AssertionError(_name)

    monkeypatch.setattr("builtins.__import__", fake_import)
    embedder = SentenceTransformerEmbedder()

    assert embedder.embed("a") == [1.0, 2.0, 3.0]
    assert embedder.embed("b") == [1.0, 2.0, 3.0]
    assert loads == 1


def test_hash_embedding_embedder_is_deterministic_and_sized() -> None:
    embedder = HashEmbeddingEmbedder(dim=8)

    first = embedder.embed("global workspace memory")
    second = embedder.embed("global workspace memory")
    other = embedder.embed("different content")

    assert len(first) == 8
    assert first == second
    assert first != other
    assert embedder.embed_batch(["a", "b"]) == [embedder.embed("a"), embedder.embed("b")]


def test_hash_embedding_embedder_rejects_invalid_dimension() -> None:
    with pytest.raises(ValueError, match="dimension"):
        HashEmbeddingEmbedder(dim=0)
