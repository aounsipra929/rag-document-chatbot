"""Step 4: FAISS vector storage. One index file per user, so users can never see each other's vectors.

Vectors are L2-normalised and stored in an inner-product index, so the score FAISS returns IS the
cosine similarity (1.0 = identical direction, ~0 = unrelated). The FAISS id of every vector is the
`chunks.id` database row, which is how a search hit becomes text + filename + page again.
"""
import threading

import faiss
import numpy as np

from config import INDEX_DIR
from services.embeddings import AIServiceError


class VectorStoreError(AIServiceError):
    pass


class VectorStore:
    def __init__(self) -> None:
        self._indexes: dict[int, faiss.Index] = {}
        self._lock = threading.RLock()

    def _path(self, user_id: int):
        return INDEX_DIR / f"user_{int(user_id)}.faiss"

    def _load(self, user_id: int, dim: int | None = None):
        index = self._indexes.get(user_id)
        if index is None:
            path = self._path(user_id)
            if path.exists():
                index = faiss.read_index(str(path))
            elif dim is not None:
                index = faiss.IndexIDMap2(faiss.IndexFlatIP(dim))
            else:
                return None
            self._indexes[user_id] = index
        if dim is not None and index.d != dim:
            raise VectorStoreError(
                "The embedding model was changed after documents were uploaded. "
                "Remove your documents and upload them again."
            )
        return index

    def _save(self, user_id: int) -> None:
        faiss.write_index(self._indexes[user_id], str(self._path(user_id)))

    def add(self, user_id: int, ids: list[int], vectors: np.ndarray) -> None:
        with self._lock:
            index = self._load(user_id, vectors.shape[1])
            index.add_with_ids(vectors, np.asarray(ids, dtype="int64"))
            self._save(user_id)

    def remove(self, user_id: int, ids: list[int]) -> None:
        with self._lock:
            index = self._load(user_id)
            if index is None or not ids:
                return
            index.remove_ids(np.asarray(ids, dtype="int64"))
            self._save(user_id)

    def search(self, user_id: int, query: np.ndarray, k: int) -> list[tuple[int, float]]:
        """Return [(chunk_id, cosine_score), ...] best first."""
        with self._lock:
            query = np.asarray(query, dtype="float32").reshape(1, -1)
            index = self._load(user_id, query.shape[1])
            if index is None or index.ntotal == 0:
                return []
            scores, ids = index.search(query, min(k, index.ntotal))
            return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]

    def drop(self, user_id: int) -> None:
        with self._lock:
            self._indexes.pop(user_id, None)
            self._path(user_id).unlink(missing_ok=True)


vector_store = VectorStore()
