from backend.rag_engine.chunker import chunk_csv, chunk_pdf, chunk_txt


def test_pdf_chunk_does_not_span_pages():
    pages = ["A" * 800, "B" * 800]
    chunks = chunk_pdf(pages, document_id="d", source="a.pdf")
    assert chunks
    for c in chunks:
        assert "A" in c.content or "B" in c.content
        assert not ("A" in c.content and "B" in c.content)
        assert c.metadata.page in (1, 2)
        assert c.metadata.type == "pdf"
        assert c.metadata.document_id == "d"


def test_csv_never_splits_a_row_and_repeats_header():
    header = "region,quarter,revenue"
    rows = ["east,Q1,10", "west,Q1,20", "east,Q2,30"]
    chunks = chunk_csv(header, rows, document_id="d", source="a.csv")
    for c in chunks:
        assert c.content.splitlines()[0] == header
        assert c.metadata.row_start <= c.metadata.row_end
        assert c.metadata.type == "csv"
    covered = []
    for c in chunks:
        covered.extend(range(c.metadata.row_start, c.metadata.row_end + 1))
    assert covered == list(range(1, 4))


def test_txt_respects_size_and_overlap():
    text = "abcdefghij" * 150  # 1500 chars
    chunks = chunk_txt(text, document_id="d", source="a.txt", type_="txt")
    assert len(chunks) >= 2
    assert chunks[0].content == text[:1000]
    assert chunks[1].content.startswith(text[800:1000])
    assert all(c.metadata.type == "txt" for c in chunks)
