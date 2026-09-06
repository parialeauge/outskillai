from backend.rag_engine.types import Chunk, ChunkMetadata
from backend.rag_engine.vectorstore import (
    build_table,
    connect_kb,
    distance_to_relevance,
    search,
    sql_where,
)
from tests.fake_embedder import FakeEmbedder


def _chunk(chunk_id: str, content: str, category: str, source: str = "a.txt") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        metadata=ChunkMetadata(
            document_id="doc_1",
            source=source,
            type="txt",
            category=category,  # type: ignore[arg-type]
            auto_category=category,  # type: ignore[arg-type]
        ),
    )


def test_sql_where_quotes_apostrophe_in_filename():
    clause = sql_where("source", ["o'reilly.pdf"])
    assert "o''reilly.pdf" in clause
    assert "source =" in clause or "source IN" in clause


def test_distance_to_relevance_is_higher_is_better_unit_interval():
    closer = distance_to_relevance(0.1)
    farther = distance_to_relevance(0.8)
    assert 0.0 <= farther <= closer <= 1.0


def test_search_where_category_pm_returns_only_pm():
    embedder = FakeEmbedder()
    chunks = [
        _chunk("c1", "project timeline milestone", "pm"),
        _chunk("c2", "revenue budget forecast", "financial"),
        _chunk("c3", "more timeline risk", "pm"),
    ]
    handle = build_table(chunks, embedder)
    hits = search(handle, "timeline", where_sql=sql_where("category", ["pm"]), k=5)
    assert hits
    assert all(h.metadata.category == "pm" for h in hits)
    assert all(0.0 <= h.metadata.relevance <= 1.0 for h in hits)
    relevances = [h.metadata.relevance for h in hits]
    assert relevances == sorted(relevances, reverse=True)
