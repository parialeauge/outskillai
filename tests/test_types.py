from backend.rag_engine.types import (
    Chunk,
    ChunkMetadata,
    DocumentInfo,
    FailedFile,
    FailedUrl,
    IngestResult,
    RetrieveResult,
)


def test_ingest_result_defaults_knowledge_base_id_to_shared():
    result = IngestResult(documents=[], failed_files=[], failed_urls=[], chunk_count=0)
    assert result.knowledge_base_id == "shared"


def test_chunk_category_is_never_none():
    meta = ChunkMetadata(
        document_id="doc_1",
        source="charter.pdf",
        type="pdf",
        category="pm",
        auto_category="pm",
        page=1,
        row_start=None,
        row_end=None,
        relevance=0.9,
        cross_category=False,
    )
    chunk = Chunk(chunk_id="chk_1", content="hello", metadata=meta)
    assert chunk.metadata.category == "pm"
    assert chunk.metadata.type == "pdf"


def test_retrieve_result_carries_primary_count_separately_from_chunks():
    result = RetrieveResult(chunks=[], primary_count=0)
    assert result.primary_count == 0
    assert result.chunks == []


def test_document_info_and_failures():
    doc = DocumentInfo(
        document_id="doc_1",
        source="charter.pdf",
        type="pdf",
        chunk_count=12,
        auto_category="uncategorized",
        category="financial",
        overridden=True,
    )
    assert doc.overridden is True
    assert FailedFile(name="bad.pdf", reason="unreadable").reason == "unreadable"
    assert FailedUrl(url="https://example.invalid", reason="timeout").url.startswith("https://")
