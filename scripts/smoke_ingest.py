"""Throwaway smoke: ingest sample_data (or a temp TXT) and print retrieved chunks.

Run from repo root: python3 -m scripts.smoke_ingest
"""

from pathlib import Path

from packages.rag_engine.retriever import ingest, reset_state, retrieve
from tests.fake_embedder import FakeEmbedder


def _classify(text: str) -> str:
    lower = text.lower()
    if "revenue" in lower or "budget" in lower or "roi" in lower:
        return "financial"
    if "timeline" in lower or "milestone" in lower or "charter" in lower:
        return "pm"
    return "uncategorized"


def main() -> None:
    reset_state()
    sample = Path(__file__).resolve().parents[1] / "sample_data"
    result = ingest(
        str(sample),
        embedder=FakeEmbedder(),
        classify_document_fn=_classify,
        fetch=lambda url: ("text/html", b"<html>example</html>"),
    )
    print("documents", len(result.documents), "chunks", result.chunk_count)
    print("failed_files", result.failed_files)
    print("failed_urls", result.failed_urls)
    hits = retrieve("shared", "timeline milestone budget revenue")
    for chunk in hits.chunks:
        print(chunk.chunk_id, chunk.metadata.category, chunk.metadata.type, chunk.content[:80].replace("\n", " "))


if __name__ == "__main__":
    main()
