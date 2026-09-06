from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from shared.config import MIN_PRIMARY, TOP_K
from backend.rag_engine.classifier import classify_chunk, classify_document
from backend.rag_engine.embeddings import Embedder
from backend.rag_engine.ingestion import (
    URLS_NAME,
    dedupe_chunks_within_document,
    load_csv,
    load_pdf,
    load_txt,
    load_urls_txt,
    scan_folder,
)
from backend.rag_engine.types import (
    Category,
    Chunk,
    DocumentInfo,
    FailedFile,
    FailedUrl,
    IngestResult,
    RetrieveResult,
)
from backend.rag_engine.vectorstore import (
    TableHandle,
    build_table,
    chunks_from_handle,
    documents_from_handle,
    search,
    sql_where,
    update_document_category,
)

STAMPS = {"financial", "pm", "capex", "policy"}
SHARED = "shared"


@dataclass
class KbState:
    handle: TableHandle | None = None
    documents: list[DocumentInfo] = field(default_factory=list)
    last_folder: str | None = None
    failed_files: list[FailedFile] = field(default_factory=list)
    failed_urls: list[FailedUrl] = field(default_factory=list)
    chunk_count: int = 0


_STATE = KbState()


def get_state() -> KbState:
    return _STATE


def reset_state() -> None:
    global _STATE
    _STATE = KbState()


def ingest(
    folder_path: str,
    stamp: str | None = None,
    *,
    merge: bool = False,
    embedder=None,
    fetch=None,
    classify_document_fn=None,
    classify_chunk_fn=None,
) -> IngestResult:
    if stamp is not None and stamp not in STAMPS | {"uncategorized"}:
        stamp = "uncategorized"

    folder = Path(folder_path)
    scan = scan_folder(folder)
    embedder = embedder or Embedder()
    classify_document_fn = classify_document_fn or classify_document
    classify_chunk_fn = classify_chunk_fn or classify_chunk

    chunks: list[Chunk] = []
    failed_files = list(scan.failed_files)
    failed_urls: list[FailedUrl] = []

    for scanned in scan.files:
        try:
            loaded, file_fails, url_fails = _load_one(scanned.path, fetch=fetch)
            failed_files.extend(file_fails)
            failed_urls.extend(url_fails)
            if stamp is not None:
                loaded = [_apply_stamp(chunk, stamp) for chunk in loaded]
            elif scanned.path.name == URLS_NAME:
                loaded = [_keep_uncategorized(chunk) for chunk in loaded]
            else:
                loaded = _classify_loaded(loaded, classify_document_fn, classify_chunk_fn)
            chunks.extend(loaded)
        except Exception as exc:  # noqa: BLE001 — keep ingest going for any format
            failed_files.append(FailedFile(name=scanned.path.name, reason=str(exc)))
            continue

    chunks = dedupe_chunks_within_document(chunks)
    state = get_state()
    if merge and state.handle is not None:
        incoming = {chunk.metadata.source for chunk in chunks}
        kept = [chunk for chunk in chunks_from_handle(state.handle) if chunk.metadata.source not in incoming]
        chunks = kept + chunks
        failed_files = list(state.failed_files) + failed_files
        failed_urls = list(state.failed_urls) + failed_urls

    handle = None
    if chunks:
        handle = build_table(chunks, embedder)
    elif merge and state.handle is not None:
        handle = state.handle

    documents = documents_from_handle(handle) if handle is not None else []
    state.handle = handle
    state.documents = documents
    state.last_folder = str(folder) if not merge else (state.last_folder or str(folder))
    state.failed_files = failed_files
    state.failed_urls = failed_urls
    state.chunk_count = sum(doc.chunk_count for doc in documents)

    return IngestResult(
        knowledge_base_id=SHARED,
        documents=documents,
        failed_files=failed_files,
        failed_urls=failed_urls,
        chunk_count=state.chunk_count,
    )


def retrieve(
    knowledge_base_id: str,
    query: str,
    top_k: int = TOP_K,
    category: str | list[str] | None = None,
    source_type: str | list[str] | None = None,
    handle: TableHandle | None = None,
) -> RetrieveResult:
    target = handle or get_state().handle
    if target is None:
        return RetrieveResult(chunks=[], primary_count=0)

    where_sql = None
    if category is not None:
        values = [category] if isinstance(category, str) else list(category)
        where_sql = sql_where("category", values)

    primary = search(target, query, where_sql=where_sql, k=top_k)
    primary_count = len(primary)
    if primary_count >= MIN_PRIMARY or category is None:
        if category is None:
            return RetrieveResult(chunks=primary, primary_count=primary_count)
        if primary_count >= MIN_PRIMARY:
            return RetrieveResult(chunks=primary, primary_count=primary_count)

    need = max(top_k - primary_count, 0)
    exclude_sql = _exclude_chunk_ids([chunk.chunk_id for chunk in primary])
    fill = search(target, query, where_sql=exclude_sql, k=need or top_k)
    flagged = [_flag_cross(chunk) for chunk in fill]
    return RetrieveResult(chunks=primary + flagged, primary_count=primary_count)


def clear(knowledge_base_id: str) -> bool:
    reset_state()
    return True


def list_documents(knowledge_base_id: str) -> list[DocumentInfo]:
    return list(get_state().documents)


def set_category(knowledge_base_id: str, document_id: str, category: str | None) -> bool:
    handle = get_state().handle
    if handle is None:
        return False
    value: Category = "uncategorized" if category is None else category  # type: ignore[assignment]
    if value not in {"financial", "pm", "capex", "policy", "uncategorized"}:
        return False
    updated = update_document_category(handle, document_id, value)
    if updated == 0:
        return False
    get_state().documents = documents_from_handle(handle)
    return True


def _load_one(path: Path, fetch=None) -> tuple[list[Chunk], list[FailedFile], list[FailedUrl]]:
    document_id = path.name
    if path.name == URLS_NAME:
        chunks, failed_urls = load_urls_txt(path, document_id=document_id, fetch=fetch)
        remapped: list[Chunk] = []
        for index, chunk in enumerate(chunks):
            remapped.append(
                chunk.model_copy(
                    update={
                        "metadata": chunk.metadata.model_copy(
                            update={"document_id": f"{document_id}_{index}"}
                        )
                    }
                )
            )
        return remapped, [], failed_urls
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        chunks, failed = load_pdf(path, document_id=document_id)
        return chunks, failed, []
    if suffix == ".csv":
        chunks, failed = load_csv(path, document_id=document_id)
        return chunks, failed, []
    chunks, failed = load_txt(path, document_id=document_id)
    return chunks, failed, []


def _coerce_category(value: str) -> Category:
    if value in {"financial", "pm", "capex", "policy", "uncategorized"}:
        return value  # type: ignore[return-value]
    return "uncategorized"


def _apply_stamp(chunk: Chunk, stamp: str) -> Chunk:
    return chunk.model_copy(
        update={
            "metadata": chunk.metadata.model_copy(
                update={
                    "category": _coerce_category(stamp),
                    "auto_category": "uncategorized",
                    "overridden": True,
                }
            )
        }
    )


def _keep_uncategorized(chunk: Chunk) -> Chunk:
    return chunk.model_copy(
        update={
            "metadata": chunk.metadata.model_copy(
                update={
                    "category": "uncategorized",
                    "auto_category": "uncategorized",
                    "overridden": False,
                }
            )
        }
    )


def _classify_loaded(chunks: list[Chunk], classify_document_fn, classify_chunk_fn) -> list[Chunk]:
    sample = " ".join(chunk.content for chunk in chunks)[:2000]
    try:
        auto = _coerce_category(str(classify_document_fn(sample) or "uncategorized"))
    except Exception:  # noqa: BLE001 — unknown formats still land in the KB
        auto = "uncategorized"
    tagged: list[Chunk] = []
    for chunk in chunks:
        try:
            category = _coerce_category(str(classify_chunk_fn(chunk.content, auto) or auto))
        except Exception:  # noqa: BLE001
            category = auto
        tagged.append(
            chunk.model_copy(
                update={
                    "metadata": chunk.metadata.model_copy(
                        update={"auto_category": auto, "category": category, "overridden": False}
                    )
                }
            )
        )
    return tagged


def _exclude_chunk_ids(chunk_ids: list[str]) -> str | None:
    if not chunk_ids:
        return None
    quoted = ", ".join("'" + chunk_id.replace("'", "''") + "'" for chunk_id in chunk_ids)
    return f"chunk_id NOT IN ({quoted})"


def _flag_cross(chunk: Chunk) -> Chunk:
    return chunk.model_copy(
        update={"metadata": chunk.metadata.model_copy(update={"cross_category": True})}
    )
