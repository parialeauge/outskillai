from pathlib import Path

import pytest

from backend.rag_engine.ingestion import IngestRejected
from backend.rag_engine.retriever import (
    clear,
    get_state,
    ingest,
    list_documents,
    reset_state,
    retrieve,
    set_category,
)
from backend.rag_engine.vectorstore import chunks_from_handle
from tests.fake_embedder import FakeEmbedder


@pytest.fixture(autouse=True)
def _clean_kb():
    reset_state()
    yield
    reset_state()


def test_merge_ingest_keeps_previous_document(tmp_path: Path):
    folder_a = tmp_path / "a"
    folder_b = tmp_path / "b"
    folder_a.mkdir()
    folder_b.mkdir()
    (folder_a / "alpha.txt").write_text("alpha timeline milestone unique-a")
    (folder_b / "beta.txt").write_text("beta revenue budget unique-b")
    ingest(str(folder_a), embedder=FakeEmbedder(), classify_document_fn=lambda text: "pm")
    result = ingest(
        str(folder_b),
        embedder=FakeEmbedder(),
        classify_document_fn=lambda text: "financial",
        merge=True,
    )
    sources = {doc.source for doc in result.documents}
    assert sources == {"alpha.txt", "beta.txt"}
    assert result.chunk_count >= 2
    both = retrieve("shared", "unique-a unique-b")
    texts = " ".join(chunk.content for chunk in both.chunks)
    assert "unique-a" in texts
    assert "unique-b" in texts


def test_merge_same_source_replaces_that_document_only(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "note.txt").write_text("old timeline unique-old")
    (first / "keep.txt").write_text("keep timeline unique-keep")
    (second / "note.txt").write_text("new revenue unique-new")
    ingest(str(first), embedder=FakeEmbedder(), classify_document_fn=lambda text: "pm")
    result = ingest(
        str(second),
        embedder=FakeEmbedder(),
        classify_document_fn=lambda text: "financial",
        merge=True,
    )
    sources = {doc.source for doc in result.documents}
    assert sources == {"note.txt", "keep.txt"}
    joined = " ".join(chunk.content for chunk in chunks_from_handle(get_state().handle))
    assert "unique-new" in joined
    assert "unique-keep" in joined
    assert "unique-old" not in joined


def test_reload_same_folder_does_not_double_chunks(tmp_path: Path):
    (tmp_path / "a.txt").write_text("timeline milestone risk")
    first = ingest(str(tmp_path), embedder=FakeEmbedder(), classify_document_fn=lambda text: "pm")
    second = ingest(str(tmp_path), embedder=FakeEmbedder(), classify_document_fn=lambda text: "pm")
    assert second.chunk_count == first.chunk_count


def test_failed_reload_leaves_previous_kb(tmp_path: Path):
    (tmp_path / "a.txt").write_text("timeline milestone risk")
    ingest(str(tmp_path), embedder=FakeEmbedder(), classify_document_fn=lambda text: "pm")
    with pytest.raises(IngestRejected):
        ingest(str(tmp_path / "missing"), embedder=FakeEmbedder())
    docs = list_documents("shared")
    assert docs
    result = retrieve("shared", "timeline", category="pm")
    assert result.chunks


def test_retrieve_uses_captured_handle_after_swap(tmp_path: Path):
    folder_a = tmp_path / "a"
    folder_b = tmp_path / "b"
    folder_a.mkdir()
    folder_b.mkdir()
    (folder_a / "a.txt").write_text("alpha timeline milestone unique-a")
    (folder_b / "b.txt").write_text("beta revenue budget unique-b")
    ingest(str(folder_a), embedder=FakeEmbedder(), classify_document_fn=lambda text: "pm")
    handle_a = get_state().handle
    ingest(str(folder_b), embedder=FakeEmbedder(), classify_document_fn=lambda text: "financial")
    old = retrieve("shared", "unique-a", category="pm", handle=handle_a)
    new = retrieve("shared", "unique-b", category="financial")
    assert any("unique-a" in c.content for c in old.chunks)
    assert any("unique-b" in c.content for c in new.chunks)


def test_set_category_overrides_all_chunks_leaves_auto(tmp_path: Path):
    (tmp_path / "a.txt").write_text("timeline milestone risk")
    ingest(str(tmp_path), embedder=FakeEmbedder(), classify_document_fn=lambda text: "pm")
    doc_id = list_documents("shared")[0].document_id
    assert set_category("shared", doc_id, "policy") is True
    doc = list_documents("shared")[0]
    assert doc.category == "policy"
    assert doc.auto_category == "pm"
    assert doc.overridden is True
    assert set_category("shared", doc_id, None) is True
    doc = list_documents("shared")[0]
    assert doc.category == "uncategorized"
    assert doc.auto_category == "pm"
    assert set_category("shared", "missing", "policy") is False


def test_reload_after_override_reclassifies(tmp_path: Path):
    (tmp_path / "a.txt").write_text("timeline milestone risk")
    ingest(str(tmp_path), embedder=FakeEmbedder(), classify_document_fn=lambda text: "pm")
    doc_id = list_documents("shared")[0].document_id
    set_category("shared", doc_id, "policy")
    ingest(str(tmp_path), embedder=FakeEmbedder(), classify_document_fn=lambda text: "pm")
    doc = list_documents("shared")[0]
    assert doc.category == "pm"
    assert doc.overridden is False


def test_reset_state_empties_documents():
    assert list_documents("shared") == []
    assert clear("shared") is True
