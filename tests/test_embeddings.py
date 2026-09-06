from tests.fake_embedder import FakeEmbedder
from backend.rag_engine.embeddings import Embedder


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _norm(a: list[float]) -> float:
    return sum(x * x for x in a) ** 0.5


def test_identical_strings_get_identical_vectors():
    embedder = Embedder(FakeEmbedder())
    a = embedder.encode(["charter budget table"])
    b = embedder.encode(["charter budget table"])
    assert a[0] == b[0]
    assert len(a[0]) == 384
    assert abs(_norm(a[0]) - 1.0) < 1e-6


def test_different_strings_get_different_non_orthogonal_vectors():
    embedder = Embedder(FakeEmbedder())
    a, b = embedder.encode(["revenue forecast", "project timeline"])
    assert a != b
    # Hash vectors in 384-d should not land orthogonal by accident.
    assert abs(_dot(a, b)) > 1e-6
