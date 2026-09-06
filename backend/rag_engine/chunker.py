from shared.config import CHUNK_OVERLAP, CHUNK_SIZE, CSV_ROWS_PER_CHUNK_MAX
from backend.rag_engine.types import Chunk, ChunkMetadata, Category, DocType


def chunk_txt(
    text: str,
    *,
    document_id: str,
    source: str,
    type_: DocType = "txt",
    category: Category = "uncategorized",
    auto_category: Category = "uncategorized",
) -> list[Chunk]:
    return _window(
        text,
        document_id=document_id,
        source=source,
        type_=type_,
        category=category,
        auto_category=auto_category,
        page=None,
    )


def chunk_pdf(
    pages: list[str],
    *,
    document_id: str,
    source: str,
    category: Category = "uncategorized",
    auto_category: Category = "uncategorized",
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for index, page_text in enumerate(pages, start=1):
        chunks.extend(
            _window(
                page_text,
                document_id=document_id,
                source=source,
                type_="pdf",
                category=category,
                auto_category=auto_category,
                page=index,
                id_prefix=f"{document_id}:p{index}",
            )
        )
    return chunks


def chunk_csv(
    header: str,
    rows: list[str],
    *,
    document_id: str,
    source: str,
    category: Category = "uncategorized",
    auto_category: Category = "uncategorized",
) -> list[Chunk]:
    chunks: list[Chunk] = []
    batch: list[str] = []
    batch_start = 1
    for index, row in enumerate(rows, start=1):
        would_exceed = batch and (
            _csv_size(header, batch + [row]) > CHUNK_SIZE
            or len(batch) >= CSV_ROWS_PER_CHUNK_MAX
        )
        if would_exceed:
            chunks.append(
                _csv_chunk(
                    header,
                    batch,
                    document_id=document_id,
                    source=source,
                    category=category,
                    auto_category=auto_category,
                    row_start=batch_start,
                    row_end=index - 1,
                    ordinal=len(chunks),
                )
            )
            batch = [row]
            batch_start = index
        else:
            batch.append(row)
    if batch:
        chunks.append(
            _csv_chunk(
                header,
                batch,
                document_id=document_id,
                source=source,
                category=category,
                auto_category=auto_category,
                row_start=batch_start,
                row_end=batch_start + len(batch) - 1,
                ordinal=len(chunks),
            )
        )
    return chunks


def _window(
    text: str,
    *,
    document_id: str,
    source: str,
    type_: DocType,
    category: Category,
    auto_category: Category,
    page: int | None,
    id_prefix: str | None = None,
) -> list[Chunk]:
    if not text:
        return []
    chunks: list[Chunk] = []
    start = 0
    ordinal = 0
    prefix = id_prefix or document_id
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append(
            Chunk(
                chunk_id=f"{prefix}:{ordinal}",
                content=text[start:end],
                metadata=ChunkMetadata(
                    document_id=document_id,
                    source=source,
                    type=type_,
                    category=category,
                    auto_category=auto_category,
                    page=page,
                ),
            )
        )
        ordinal += 1
        if end == len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def _csv_size(header: str, rows: list[str]) -> int:
    return len("\n".join([header, *rows]))


def _csv_chunk(
    header: str,
    rows: list[str],
    *,
    document_id: str,
    source: str,
    category: Category,
    auto_category: Category,
    row_start: int,
    row_end: int,
    ordinal: int,
) -> Chunk:
    return Chunk(
        chunk_id=f"{document_id}:csv:{ordinal}",
        content="\n".join([header, *rows]),
        metadata=ChunkMetadata(
            document_id=document_id,
            source=source,
            type="csv",
            category=category,
            auto_category=auto_category,
            row_start=row_start,
            row_end=row_end,
        ),
    )
