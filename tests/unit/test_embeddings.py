"""Embedding provider contract regressions."""

import numpy as np

from gwt_context.infrastructure.embeddings import SentenceTransformerEmbedder


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
