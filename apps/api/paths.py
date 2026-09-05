from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import HTTPException


def normalize_folder_path(folder_path: str) -> str:
    text = (folder_path or "").strip().strip("\"'")
    if text.startswith("file:"):
        parsed = urlparse(text)
        text = unquote(parsed.path or "")
    return str(Path(text).expanduser())


def resolve_ingest_path(folder_path: str, *, root: str | None = None) -> Path:
    root_value = root if root is not None else os.getenv("ALLOWED_INGEST_ROOT", "")
    try:
        allowed = Path(root_value).expanduser().resolve(strict=True)
        target = Path(normalize_folder_path(folder_path)).resolve(strict=True)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bad_folder",
                "message": "Folder is empty or missing — scan is top-level files only.",
            },
        ) from error
    except OSError as error:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_folder", "message": str(error)},
        ) from error

    if os.path.commonpath([str(allowed), str(target)]) != str(allowed):
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden_path", "message": "Path is outside ALLOWED_INGEST_ROOT."},
        )
    if not target.is_dir():
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bad_folder",
                "message": "Folder is empty or missing — scan is top-level files only.",
            },
        )
    return target
