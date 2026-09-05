from __future__ import annotations

import tempfile
import uuid
from dataclasses import dataclass
from typing import Any

import lancedb

from packages.rag_engine.embeddings import EmbeddingModel
from packages.rag_engine.types import Category, Chunk, ChunkMetadata


@dataclass
class TableHandle:
    db: Any
    table: Any
    name: str
    embedder: EmbeddingModel


def connect_kb():
    return lancedb.connect(tempfile.mkdtemp(prefix="outskill-kb-"))


def sql_where(column: str, values: list[str]) -> str:
    if not values:
        raise ValueError("sql_where requires at least one value")
    quoted = [_quote(value) for value in values]
    if len(quoted) == 1:
        return f"{column} = {quoted[0]}"
    return f"{column} IN ({', '.join(quoted)})"


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def distance_to_relevance(distance: float) -> float:
    return max(0.0, min(1.0, 1.0 - float(distance)))


def build_table(chunks: list[Chunk], embedder: EmbeddingModel) -> TableHandle:
    db = connect_kb()
    name = f"kb_{uuid.uuid4().hex}"
    vectors = embedder.encode([chunk.content for chunk in chunks])
    rows = [_row(chunk, vector) for chunk, vector in zip(chunks, vectors, strict=True)]
    table = db.create_table(name, rows)
    return TableHandle(db=db, table=table, name=name, embedder=embedder)


def search(
    handle: TableHandle,
    query: str,
    where_sql: str | None = None,
    k: int = 5,
) -> list[Chunk]:
    vector = handle.embedder.encode([query])[0]
    builder = handle.table.search(vector)
    if where_sql:
        builder = builder.where(where_sql, prefilter=True)
    rows = builder.limit(k).to_list()
    chunks = [_from_row(row) for row in rows]
    chunks.sort(key=lambda chunk: chunk.metadata.relevance, reverse=True)
    return chunks


def _row(chunk: Chunk, vector: list[float]) -> dict[str, Any]:
    meta = chunk.metadata
    category: Category = meta.category or "uncategorized"
    auto: Category = meta.auto_category or "uncategorized"
    return {
        "chunk_id": chunk.chunk_id,
        "content": chunk.content,
        "vector": vector,
        "document_id": meta.document_id,
        "source": meta.source,
        "type": meta.type,
        "category": category,
        "auto_category": auto,
        "page": meta.page,
        "row_start": meta.row_start,
        "row_end": meta.row_end,
        "cross_category": bool(meta.cross_category),
        "overridden": bool(meta.overridden),
    }


def _from_row(row: dict[str, Any]) -> Chunk:
    relevance = distance_to_relevance(row.get("_distance", 0.0))
    return Chunk(
        chunk_id=row["chunk_id"],
        content=row["content"],
        metadata=ChunkMetadata(
            document_id=row["document_id"],
            source=row["source"],
            type=row["type"],
            category=row["category"],
            auto_category=row["auto_category"],
            page=row.get("page"),
            row_start=row.get("row_start"),
            row_end=row.get("row_end"),
            relevance=relevance,
            cross_category=bool(row.get("cross_category", False)),
            overridden=bool(row.get("overridden", False)),
        ),
    )


def update_document_category(handle: TableHandle, document_id: str, category: str) -> int:
    result = handle.table.update(
        where=sql_where("document_id", [document_id]),
        values={"category": category, "overridden": True},
    )
    return int(getattr(result, "rows_updated", 0))


def documents_from_handle(handle: TableHandle) -> list:
    from packages.rag_engine.types import DocumentInfo

    frame = handle.table.to_pandas()
    docs: dict[str, DocumentInfo] = {}
    for row in frame.to_dict(orient="records"):
        document_id = row["document_id"]
        if document_id not in docs:
            docs[document_id] = DocumentInfo(
                document_id=document_id,
                source=row["source"],
                type=row["type"],
                chunk_count=0,
                auto_category=row["auto_category"],
                category=row["category"],
                overridden=bool(row.get("overridden", False)),
            )
        docs[document_id].chunk_count += 1
    return list(docs.values())
