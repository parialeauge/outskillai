import pytest

from backend.rag_engine.retriever import ingest, reset_state, retrieve
from tests.fake_embedder import FakeEmbedder


@pytest.fixture(autouse=True)
def _clean_kb():
    reset_state()
    yield
    reset_state()


def _pm_files(tmp_path, n: int, prefix: str = "pm"):
    for i in range(n):
        (tmp_path / f"{prefix}{i}.txt").write_text(
            f"timeline milestone risk resource allocation number {i}"
        )


def _financial_files(tmp_path, n: int):
    for i in range(n):
        (tmp_path / f"fin{i}.txt").write_text(
            f"revenue budget forecast roi operating cost {i}"
        )


def test_enough_pm_primary_has_no_cross_category(tmp_path):
    _pm_files(tmp_path, 4)
    ingest(str(tmp_path), embedder=FakeEmbedder(), classify_document_fn=lambda text: "pm")
    result = retrieve("shared", "timeline milestone", category="pm")
    assert result.primary_count >= 3
    assert all(c.metadata.category == "pm" for c in result.chunks)
    assert all(c.metadata.cross_category is False for c in result.chunks)


def test_zero_pm_backfills_all_cross_category(tmp_path):
    _financial_files(tmp_path, 4)
    ingest(str(tmp_path), embedder=FakeEmbedder(), classify_document_fn=lambda text: "financial")
    result = retrieve("shared", "revenue budget", category="pm")
    assert result.primary_count == 0
    assert result.chunks
    assert all(c.metadata.cross_category is True for c in result.chunks)


def test_primary_count_is_in_category_only(tmp_path):
    _pm_files(tmp_path, 1)
    _financial_files(tmp_path, 4)
    ingest(
        str(tmp_path),
        embedder=FakeEmbedder(),
        classify_document_fn=lambda text: "pm" if "timeline" in text else "financial",
    )
    result = retrieve("shared", "timeline revenue", category="pm")
    assert result.primary_count == sum(1 for c in result.chunks if not c.metadata.cross_category)
    assert result.primary_count != len(result.chunks) or result.primary_count == 0


def test_unstamped_web_does_not_count_as_pm_primary(tmp_path):
    _financial_files(tmp_path, 1)
    (tmp_path / "urls.txt").write_text("https://ok.example\n")
    ingest(
        str(tmp_path),
        embedder=FakeEmbedder(),
        fetch=lambda url: ("text/html", b"<html>web</html>"),
        classify_document_fn=lambda text: "financial",
    )
    result = retrieve("shared", "web", category="pm")
    assert result.primary_count == 0
    web = [c for c in result.chunks if c.metadata.type == "web"]
    assert web
    assert all(c.metadata.cross_category is True for c in web)


def test_stamped_web_counts_toward_pm_primary(tmp_path):
    (tmp_path / "urls.txt").write_text("https://ok.example\n")
    ingest(
        str(tmp_path),
        stamp="pm",
        embedder=FakeEmbedder(),
        fetch=lambda url: ("text/html", b"<html>timeline milestone risk</html>"),
    )
    result = retrieve("shared", "timeline", category="pm")
    web = [c for c in result.chunks if c.metadata.type == "web"]
    assert web
    assert result.primary_count >= 1
    assert all(c.metadata.cross_category is False for c in web)


def test_exactly_min_primary_does_not_backfill(tmp_path):
    _pm_files(tmp_path, 3)
    _financial_files(tmp_path, 5)
    ingest(
        str(tmp_path),
        embedder=FakeEmbedder(),
        classify_document_fn=lambda text: "pm" if "timeline" in text else "financial",
    )
    result = retrieve("shared", "timeline milestone", category="pm", top_k=5)
    assert result.primary_count == 3
    assert len(result.chunks) == 3
    assert all(c.metadata.cross_category is False for c in result.chunks)


def test_prefilter_returns_all_three_pm_of_twenty(tmp_path):
    _pm_files(tmp_path, 3)
    _financial_files(tmp_path, 17)
    ingest(
        str(tmp_path),
        embedder=FakeEmbedder(),
        classify_document_fn=lambda text: "pm" if "timeline" in text else "financial",
    )
    result = retrieve("shared", "timeline", category="pm", top_k=5)
    assert result.primary_count == 3
    assert len([c for c in result.chunks if c.metadata.category == "pm" and not c.metadata.cross_category]) == 3
