from pathlib import Path

import pytest

from packages.rag_engine.ingestion import IngestRejected, dedupe_chunks_within_document, scan_folder
from packages.rag_engine.types import Chunk, ChunkMetadata


def _chunk(document_id: str, content: str, chunk_id: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        metadata=ChunkMetadata(
            document_id=document_id,
            source=f"{document_id}.txt",
            type="txt",
            category="uncategorized",
            auto_category="uncategorized",
        ),
    )


def test_missing_path_is_bad_folder(tmp_path: Path):
    with pytest.raises(IngestRejected) as exc:
        scan_folder(tmp_path / "nope")
    assert exc.value.code == "bad_folder"


def test_subdirectory_only_folder_is_bad_folder_and_mentions_flat(tmp_path: Path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "hidden.pdf").write_bytes(b"%PDF")
    with pytest.raises(IngestRejected) as exc:
        scan_folder(tmp_path)
    assert exc.value.code == "bad_folder"
    assert "flat" in str(exc.value).lower()


def test_over_max_files_raises_before_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import packages.rag_engine.ingestion as ingestion

    monkeypatch.setattr(ingestion, "MAX_FILES", 2)
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("x")
    with pytest.raises(IngestRejected) as exc:
        scan_folder(tmp_path)
    assert exc.value.code == "bad_folder"
    assert "3" in str(exc.value)


def test_oversized_file_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import packages.rag_engine.ingestion as ingestion

    monkeypatch.setattr(ingestion, "MAX_FILE_MB", 1)
    (tmp_path / "ok.txt").write_text("hello")
    (tmp_path / "huge.txt").write_bytes(b"x" * (2 * 1024 * 1024))
    result = scan_folder(tmp_path)
    names = {item.path.name for item in result.files}
    assert names == {"ok.txt"}
    assert any(f.name == "huge.txt" for f in result.failed_files)


def test_dedupe_collapses_within_one_document_keeps_across_documents():
    same = "boilerplate header"
    chunks = [
        _chunk("doc_a", same, "a1"),
        _chunk("doc_a", same, "a2"),
        _chunk("doc_b", same, "b1"),
    ]
    out = dedupe_chunks_within_document(chunks)
    ids = [c.chunk_id for c in out]
    assert ids == ["a1", "b1"]
