from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from shared.config import (
    MAX_FILE_MB,
    MAX_URL_BYTES,
    MAX_URLS,
    URL_FETCH_CONCURRENCY,
    URL_FETCH_TIMEOUT,
)
from backend.rag_engine.chunker import chunk_csv, chunk_pdf, chunk_txt
from backend.rag_engine.types import Chunk, FailedFile, FailedUrl

URLS_NAME = "urls.txt"


class IngestRejected(Exception):
    code = "bad_folder"

    def __init__(self, message: str) -> None:
        super().__init__(message)


@dataclass
class ScannedFile:
    path: Path
    size_bytes: int


@dataclass
class ScanResult:
    files: list[ScannedFile] = field(default_factory=list)
    failed_files: list[FailedFile] = field(default_factory=list)


def scan_folder(path: Path) -> ScanResult:
    folder = Path(path)
    if not folder.exists() or not folder.is_dir():
        raise IngestRejected("Folder is missing or is not a directory.")

    candidates: list[Path] = []
    for entry in sorted(folder.iterdir()):
        if not entry.is_file():
            continue
        if entry.name.startswith("."):
            continue
        candidates.append(entry)

    if not candidates:
        raise IngestRejected(
            "No top-level files to ingest. The scan is flat — subdirectories are not scanned."
        )

    limit = MAX_FILE_MB * 1024 * 1024
    result = ScanResult()
    for candidate in candidates:
        size = candidate.stat().st_size
        if size > limit:
            result.failed_files.append(
                FailedFile(name=candidate.name, reason=f"file exceeds {MAX_FILE_MB} MB ({size} bytes)")
            )
            continue
        result.files.append(ScannedFile(path=candidate, size_bytes=size))
    return result


def dedupe_chunks_within_document(chunks: list[Chunk]) -> list[Chunk]:
    seen: set[tuple[str, str]] = set()
    kept: list[Chunk] = []
    for chunk in chunks:
        digest = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
        key = (chunk.metadata.document_id, digest)
        if key in seen:
            continue
        seen.add(key)
        kept.append(chunk)
    return kept


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def load_txt(path: Path, document_id: str) -> tuple[list[Chunk], list[FailedFile]]:
    try:
        text = _read_text(path)
    except OSError as exc:
        return [], [FailedFile(name=path.name, reason=str(exc))]
    return chunk_txt(text, document_id=document_id, source=path.name, type_="txt"), []


def load_csv(path: Path, document_id: str) -> tuple[list[Chunk], list[FailedFile]]:
    try:
        text = _read_text(path)
        import io

        import pandas as pd

        frame = pd.read_csv(io.StringIO(text))
        header = ",".join(str(column) for column in frame.columns)
        rows: list[str] = []
        for row in frame.itertuples(index=False, name=None):
            cells = ["" if pd.isna(value) else str(value) for value in row]
            rows.append(",".join(cells))
        return chunk_csv(header, rows, document_id=document_id, source=path.name), []
    except Exception as exc:  # noqa: BLE001 — skip unreadable files
        return [], [FailedFile(name=path.name, reason=str(exc))]


def load_pdf(path: Path, document_id: str) -> tuple[list[Chunk], list[FailedFile]]:
    try:
        import pymupdf

        document = pymupdf.open(path)
        pages = [page.get_text() for page in document]
        document.close()
    except Exception as exc:  # noqa: BLE001 — skip unreadable files
        return [], [FailedFile(name=path.name, reason=str(exc))]
    return chunk_pdf(pages, document_id=document_id, source=path.name), []


def _content_type_allowed(content_type: str) -> bool:
    main = content_type.split(";", 1)[0].strip().lower()
    return main.startswith("text/") or main == "application/xhtml+xml"


def _http_fetch(url: str) -> tuple[str, bytes]:
    import httpx

    with httpx.Client(timeout=URL_FETCH_TIMEOUT, follow_redirects=True) as client:
        with client.stream("GET", url) as response:
            content_type = response.headers.get("content-type", "")
            body = b""
            for piece in response.iter_bytes():
                body += piece
                if len(body) > MAX_URL_BYTES:
                    break
            return content_type, body


def load_urls_txt(
    path: Path,
    document_id: str,
    fetch=None,
) -> tuple[list[Chunk], list[FailedUrl]]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    text = _read_text(path)
    urls = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    failed: list[FailedUrl] = []
    kept = urls[:MAX_URLS]
    for extra in urls[MAX_URLS:]:
        failed.append(FailedUrl(url=extra, reason=f"over MAX_URLS cap of {MAX_URLS}"))

    getter = fetch or _http_fetch
    chunks: list[Chunk] = []

    def one(url: str) -> tuple[list[Chunk], FailedUrl | None]:
        try:
            content_type, body = getter(url)
        except Exception as exc:  # noqa: BLE001 — skip bad URLs
            return [], FailedUrl(url=url, reason=f"timeout or fetch error: {exc}")
        if not _content_type_allowed(content_type):
            return [], FailedUrl(url=url, reason=f"unsupported content-type {content_type}")
        if len(body) > MAX_URL_BYTES:
            return [], FailedUrl(url=url, reason=f"response exceeds MAX_URL_BYTES ({len(body)} bytes)")
        page = body.decode("utf-8", errors="replace")
        return (
            chunk_txt(page, document_id=document_id, source=url, type_="web"),
            None,
        )

    with ThreadPoolExecutor(max_workers=URL_FETCH_CONCURRENCY) as pool:
        futures = {pool.submit(one, url): url for url in kept}
        for future in as_completed(futures):
            got, error = future.result()
            chunks.extend(got)
            if error is not None:
                failed.append(error)
    return chunks, failed

