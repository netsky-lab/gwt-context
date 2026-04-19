"""Vector index for cosine similarity search.

Pure numpy implementation — no native dependencies.
For production scale (>100K items), swap to hnswlib/FAISS.
Sufficient for our use case: typical sessions have <10K items.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


class VectorIndex:
    """Numpy-backed brute-force cosine similarity index.

    Stores vectors in a matrix, searches via dot product on normalized vectors.
    O(n) search, but fast enough for <10K items thanks to numpy vectorization.
    """

    def __init__(
        self,
        dim: int = 384,
        max_elements: int = 100_000,
        path: Path | None = None,
    ) -> None:
        self._dim = dim
        self._path = path
        self._id_to_idx: dict[str, int] = {}
        self._idx_to_id: dict[int, str] = {}
        self._vectors: list[NDArray[np.float32]] = []  # Normalized vectors

        if path and path.with_suffix(".json").exists():
            self._load(path)

    @property
    def count(self) -> int:
        return len(self._id_to_idx)

    def add(self, item_id: str, embedding: list[float]) -> None:
        """Add or update a vector for item_id."""
        vec = np.array(embedding, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        if item_id in self._id_to_idx:
            idx = self._id_to_idx[item_id]
            self._vectors[idx] = vec
        else:
            idx = len(self._vectors)
            self._id_to_idx[item_id] = idx
            self._idx_to_id[idx] = item_id
            self._vectors.append(vec)

    def remove(self, item_id: str) -> None:
        """Remove item from index (marks as zero vector)."""
        if item_id in self._id_to_idx:
            idx = self._id_to_idx[item_id]
            self._vectors[idx] = np.zeros(self._dim, dtype=np.float32)
            del self._id_to_idx[item_id]
            del self._idx_to_id[idx]

    def query(
        self, embedding: list[float], k: int = 10
    ) -> list[tuple[str, float]]:
        """Find k nearest neighbors by cosine similarity.

        Returns list of (item_id, similarity) pairs, sorted descending.
        """
        if self.count == 0:
            return []

        query_vec = np.array(embedding, dtype=np.float32)
        norm = np.linalg.norm(query_vec)
        if norm > 0:
            query_vec = query_vec / norm

        # Stack all vectors and compute dot products (cosine sim on normalized vecs)
        matrix = np.stack(self._vectors)
        similarities = matrix @ query_vec

        # Get top-k indices
        actual_k = min(k, self.count)
        top_indices = np.argsort(similarities)[::-1]

        results = []
        for idx in top_indices:
            idx = int(idx)
            if idx in self._idx_to_id:
                results.append((self._idx_to_id[idx], float(similarities[idx])))
                if len(results) >= actual_k:
                    break
        return results

    def save(self, path: Path | None = None) -> None:
        """Persist index to disk as JSON + numpy binary."""
        save_path = path or self._path
        if save_path is None:
            return

        data = {
            "dim": self._dim,
            "id_to_idx": self._id_to_idx,
            "idx_to_id": {str(k): v for k, v in self._idx_to_id.items()},
        }
        meta_path = save_path.with_suffix(".json")
        vec_path = save_path.with_suffix(".npy")

        with open(meta_path, "w") as f:
            json.dump(data, f)

        if self._vectors:
            np.save(vec_path, np.stack(self._vectors))

    def _load(self, path: Path) -> None:
        """Load index from disk."""
        meta_path = path.with_suffix(".json")
        vec_path = path.with_suffix(".npy")

        if not meta_path.exists():
            return

        with open(meta_path) as f:
            data = json.load(f)

        self._dim = data["dim"]
        self._id_to_idx = data["id_to_idx"]
        self._idx_to_id = {int(k): v for k, v in data["idx_to_id"].items()}

        if vec_path.exists():
            matrix = np.load(vec_path)
            self._vectors = [matrix[i] for i in range(len(matrix))]
