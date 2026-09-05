from pathlib import Path

import pytest

from packages.rag_engine.ingestion import IngestRejected
from packages.rag_engine.retriever import (
    clear,
    ingest,
    list_documents,
    reset_state,
    retrieve,
    set_category,
)
from tests.fake_embedder import FakeEmbedder


@pytest.fixture(autouse=True)
def _clean_kb():
    reset_state()
    yield
    reset_state()


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
    from packages.rag_engine.retriever import get_state

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
