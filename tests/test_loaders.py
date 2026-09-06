from pathlib import Path

import pymupdf
import pytest

from backend.rag_engine.ingestion import load_csv, load_pdf, load_urls_txt
from backend.rag_engine.types import FailedUrl


def test_latin1_csv_ingests(tmp_path: Path):
    path = tmp_path / "latin.csv"
    path.write_bytes("region,note\nwest,caf\xe9\n".encode("latin-1"))
    chunks, failed = load_csv(path, document_id="doc_csv")
    assert failed == []
    assert chunks
    assert "caf" in chunks[0].content


def test_urls_over_max_are_failed_urls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.rag_engine.ingestion as ingestion

    monkeypatch.setattr(ingestion, "MAX_URLS", 1)
    path = tmp_path / "urls.txt"
    path.write_text("https://example.com/a\nhttps://example.com/b\n")

    def fake_fetch(url: str) -> tuple[str, bytes]:
        return ("text/html", b"<html>ok</html>")

    chunks, failed = load_urls_txt(path, document_id="doc_web", fetch=fake_fetch)
    assert len(chunks) == 1
    assert any(item.url == "https://example.com/b" for item in failed)


def test_url_over_bytes_and_non_text_have_distinct_reasons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.rag_engine.ingestion as ingestion

    monkeypatch.setattr(ingestion, "MAX_URL_BYTES", 8)
    path = tmp_path / "urls.txt"
    path.write_text("https://example.com/big\nhttps://example.com/pdf\n")

    def fake_fetch(url: str) -> tuple[str, bytes]:
        if url.endswith("big"):
            return ("text/html", b"0123456789")
        return ("application/pdf", b"%PDF")

    chunks, failed = load_urls_txt(path, document_id="doc_web", fetch=fake_fetch)
    assert chunks == []
    reasons = {item.reason for item in failed}
    assert len(reasons) == 2
    assert any("byte" in item.reason.lower() or "size" in item.reason.lower() for item in failed)
    assert any("content-type" in item.reason.lower() or "type" in item.reason.lower() for item in failed)
    assert all(isinstance(item, FailedUrl) for item in failed)


def test_pdf_loader_yields_page_chunks(tmp_path: Path):
    path = tmp_path / "one.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello page one")
    doc.save(path)
    doc.close()
    chunks, failed = load_pdf(path, document_id="doc_pdf")
    assert failed == []
    assert chunks
    assert chunks[0].metadata.page == 1
    assert "Hello page one" in chunks[0].content
