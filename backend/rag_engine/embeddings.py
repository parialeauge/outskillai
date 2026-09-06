"""Embedding interface. Callers wrap encode() with asyncio.to_thread."""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingModel(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...


class Embedder:
    def __init__(self, model: EmbeddingModel | None = None) -> None:
        self._model = model if model is not None else _load_sentence_transformer()

    def encode(self, texts: list[str]) -> list[list[float]]:
        encoded = self._model.encode(texts)
        return [list(vector) for vector in encoded]


def _load_sentence_transformer() -> EmbeddingModel:
    from sentence_transformers import SentenceTransformer

    name = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    return SentenceTransformer(name)
