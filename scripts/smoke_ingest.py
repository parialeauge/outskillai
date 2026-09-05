"""Throwaway smoke: ingest one TXT and print retrieved chunks.

Run from repo root: python3 -m scripts.smoke_ingest
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from packages.rag_engine.retriever import ingest, retrieve
from tests.fake_embedder import FakeEmbedder


def main() -> None:
    with TemporaryDirectory() as folder:
        path = Path(folder) / "note.txt"
        path.write_text("timeline milestone risk resource allocation")
        result = ingest(folder, embedder=FakeEmbedder(), classify_document_fn=lambda text: "pm")
        print("documents", result.chunk_count)
        hits = retrieve("shared", "timeline", category="pm")
        for chunk in hits.chunks:
            print(chunk.chunk_id, chunk.metadata.category, chunk.content[:80])


if __name__ == "__main__":
    main()
