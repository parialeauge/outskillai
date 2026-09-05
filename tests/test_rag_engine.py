from pathlib import Path

import pymupdf
import pytest

from packages.rag_engine.retriever import ingest, reset_state
from packages.rag_engine.ingestion import IngestRejected
from tests.fake_embedder import FakeEmbedder


@pytest.fixture(autouse=True)
def _clean_kb():
    reset_state()
    yield
    reset_state()


def _pdf(path: Path, texts: list[str]) -> None:
    doc = pymupdf.open()
    for text in texts:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def _fetch_ok(url: str) -> tuple[str, bytes]:
    return ("text/html", b"<html>web snippet</html>")


def test_mixed_folder_ingest_populates_documents_and_failures(tmp_path: Path):
    _pdf(tmp_path / "charter.pdf", ["timeline milestone risk charter"])
    (tmp_path / "budget.csv").write_text("region,revenue\neast,10\nwest,20\n")
    (tmp_path / "notes.txt").write_text("lorem ipsum dolor sit amet")
    (tmp_path / "urls.txt").write_text("https://ok.example\nhttps://bad.example\n")

    def fetch(url: str) -> tuple[str, bytes]:
        if "bad" in url:
            return ("application/pdf", b"%PDF")
        return ("text/html", b"<html>ok</html>")

    result = ingest(
        str(tmp_path),
        embedder=FakeEmbedder(),
        fetch=fetch,
        classify_document_fn=lambda text: "uncategorized",
    )
    sources = {d.source for d in result.documents}
    assert "charter.pdf" in sources
    assert "budget.csv" in sources
    assert result.failed_urls
    assert result.knowledge_base_id == "shared"


def test_csv_chunks_keep_header_and_row_range(tmp_path: Path):
    (tmp_path / "budget.csv").write_text("region,revenue\neast,10\nwest,20\n")
    result = ingest(str(tmp_path), embedder=FakeEmbedder())
    from packages.rag_engine.retriever import retrieve

    hits = retrieve("shared", "revenue", category="uncategorized")
    csv = [c for c in hits.chunks if c.metadata.type == "csv"]
    assert csv
    for chunk in csv:
        assert chunk.content.splitlines()[0] == "region,revenue"
        assert chunk.metadata.row_start <= chunk.metadata.row_end


def test_pdf_chunks_do_not_span_pages(tmp_path: Path):
    _pdf(tmp_path / "two.pdf", ["AAAA page one timeline", "BBBB page two timeline"])
    ingest(str(tmp_path), embedder=FakeEmbedder(), classify_document_fn=lambda text: "pm")
    from packages.rag_engine.retriever import retrieve

    hits = retrieve("shared", "timeline", category="pm")
    for chunk in hits.chunks:
        if chunk.metadata.type == "pdf":
            assert not ("AAAA" in chunk.content and "BBBB" in chunk.content)
            assert chunk.metadata.page in (1, 2)


def test_boilerplate_inside_one_document_collapses(tmp_path: Path):
    (tmp_path / "repeat.txt").write_text("A" * 1800)
    result = ingest(str(tmp_path), embedder=FakeEmbedder())
    assert result.documents[0].chunk_count == 1


def test_identical_content_in_two_files_stays_two_chunks(tmp_path: Path):
    (tmp_path / "a.txt").write_text("A" * 1800)
    (tmp_path / "b.txt").write_text("A" * 1800)
    result = ingest(str(tmp_path), embedder=FakeEmbedder())
    assert len(result.documents) == 2
    assert all(doc.chunk_count == 1 for doc in result.documents)
    assert result.chunk_count == 2


def test_unmatched_document_is_uncategorized(tmp_path: Path):
    (tmp_path / "lorem.txt").write_text("lorem ipsum dolor sit amet")
    result = ingest(
        str(tmp_path),
        embedder=FakeEmbedder(),
        classify_document_fn=lambda text: "uncategorized",
    )
    assert result.documents[0].auto_category == "uncategorized"


def test_mixed_document_chunk_categories(tmp_path: Path):
    financial = ("revenue budget forecast roi operating " * 80).strip()
    pm = ("timeline milestone risk resource allocation " * 80).strip()
    (tmp_path / "mixed.txt").write_text(financial + "\n" + pm)
    ingest(str(tmp_path), embedder=FakeEmbedder(), classify_document_fn=lambda text: "pm")
    from packages.rag_engine.retriever import retrieve

    all_hits = retrieve("shared", "project", category=None, top_k=20)
    cats = {c.metadata.category for c in all_hits.chunks}
    assert "financial" in cats
    assert "pm" in cats


def test_stamp_financial_skips_classifier_and_stamps_urls(tmp_path: Path):
    calls = []

    def classify(text: str) -> str:
        calls.append(text)
        return "pm"

    (tmp_path / "notes.txt").write_text("lorem")
    (tmp_path / "urls.txt").write_text("https://ok.example\n")
    result = ingest(
        str(tmp_path),
        stamp="financial",
        embedder=FakeEmbedder(),
        fetch=_fetch_ok,
        classify_document_fn=classify,
    )
    assert calls == []
    assert all(d.category == "financial" and d.overridden and d.auto_category == "uncategorized" for d in result.documents)


def test_stamp_none_leaves_urls_uncategorized(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("timeline milestone risk")
    (tmp_path / "urls.txt").write_text("https://ok.example\n")
    result = ingest(
        str(tmp_path),
        embedder=FakeEmbedder(),
        fetch=_fetch_ok,
        classify_document_fn=lambda text: "pm",
    )
    by_source = {d.source: d for d in result.documents}
    assert by_source["notes.txt"].category == "pm"
    web = [d for d in result.documents if d.type == "web"]
    assert web
    assert all(d.category == "uncategorized" for d in web)


def test_stamp_uncategorized_rejects_without_swap(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("hello")
    with pytest.raises(IngestRejected) as exc:
        ingest(str(tmp_path), stamp="uncategorized", embedder=FakeEmbedder())
    assert exc.value.code == "bad_folder"
    from packages.rag_engine.retriever import list_documents

    assert list_documents("shared") == []


def test_subdirectory_only_rejected(tmp_path: Path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "hidden.pdf").write_bytes(b"%PDF")
    with pytest.raises(IngestRejected):
        ingest(str(tmp_path), embedder=FakeEmbedder())


def test_max_files_and_max_file_mb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import packages.rag_engine.ingestion as ingestion

    monkeypatch.setattr(ingestion, "MAX_FILES", 2)
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("x")
    with pytest.raises(IngestRejected):
        ingest(str(tmp_path), embedder=FakeEmbedder())

    monkeypatch.setattr(ingestion, "MAX_FILES", 40)
    monkeypatch.setattr(ingestion, "MAX_FILE_MB", 1)
    folder = tmp_path / "sized"
    folder.mkdir()
    (folder / "ok.txt").write_text("timeline milestone risk")
    (folder / "huge.txt").write_bytes(b"x" * (2 * 1024 * 1024))
    result = ingest(str(folder), embedder=FakeEmbedder(), classify_document_fn=lambda text: "pm")
    assert any(f.name == "huge.txt" for f in result.failed_files)
    assert result.documents


def test_urls_failures_have_distinct_reasons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import packages.rag_engine.ingestion as ingestion

    monkeypatch.setattr(ingestion, "MAX_URLS", 1)
    monkeypatch.setattr(ingestion, "MAX_URL_BYTES", 8)
    (tmp_path / "urls.txt").write_text(
        "https://example.com/keep\nhttps://example.com/extra\nhttps://example.com/big\n"
    )

    def fetch(url: str) -> tuple[str, bytes]:
        if url.endswith("keep"):
            return ("text/html", b"<html>ok</html>")
        if url.endswith("big"):
            return ("text/html", b"0123456789")
        return ("application/pdf", b"%PDF")

    result = ingest(str(tmp_path), embedder=FakeEmbedder(), fetch=fetch)
    reasons = {item.reason for item in result.failed_urls}
    assert len(reasons) >= 1


def test_latin1_csv_ingests(tmp_path: Path):
    (tmp_path / "latin.csv").write_bytes("region,note\nwest,caf\xe9\n".encode("latin-1"))
    result = ingest(str(tmp_path), embedder=FakeEmbedder())
    assert result.documents
    assert result.failed_files == []
