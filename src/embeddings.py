"""Optional local embeddings helpers.

The project can run without embeddings (default). If you enable embeddings in
config.py (EMBEDDINGS_ENABLED=True), we will try to load a SentenceTransformer
model locally. If the dependency is missing, we fall back gracefully.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from .config import EMBEDDINGS_ENABLED, EMBEDDING_MODEL_NAME


@lru_cache(maxsize=1)
def _load_model():
    if not EMBEDDINGS_ENABLED:
        return None
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception:
        return None
    try:
        return SentenceTransformer(EMBEDDING_MODEL_NAME)
    except Exception:
        return None


def available() -> bool:
    return _load_model() is not None


def embed(texts: List[str]) -> Optional[List[List[float]]]:
    """Return embeddings as python lists, or None if unavailable."""
    model = _load_model()
    if model is None:
        return None
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    # numpy -> list
    return [v.tolist() for v in vecs]
