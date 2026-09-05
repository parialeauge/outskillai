"""Hash-based unit vectors for deterministic rag_engine tests."""

from __future__ import annotations

import hashlib
import math

DIM = 384


class FakeEmbedder:
    def encode(self, texts: list[str]) -> list[list[float]]:
        return [_hash_vector(text) for text in texts]


def _hash_vector(text: str) -> list[float]:
    vals: list[float] = []
    seed = text.encode("utf-8")
    i = 0
    while len(vals) < DIM:
        digest = hashlib.sha256(seed + i.to_bytes(4, "big")).digest()
        for byte in digest:
            vals.append((byte / 127.5) - 1.0)
            if len(vals) == DIM:
                break
        i += 1
    norm = math.sqrt(sum(v * v for v in vals)) or 1.0
    return [v / norm for v in vals]
