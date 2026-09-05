from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from shared.config import MAX_FILE_MB, MAX_FILES
from packages.rag_engine.types import Chunk, FailedFile

INGESTABLE_SUFFIXES = {".pdf", ".csv", ".txt"}
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
        if entry.name == URLS_NAME or entry.suffix.lower() in INGESTABLE_SUFFIXES:
            candidates.append(entry)

    if not candidates:
        raise IngestRejected(
            "No top-level pdf, csv, txt, or urls.txt files to ingest. "
            "The scan is flat — subdirectories are not scanned."
        )

    if len(candidates) > MAX_FILES:
        raise IngestRejected(
            f"Folder has {len(candidates)} ingestable files, over the cap of {MAX_FILES}."
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
