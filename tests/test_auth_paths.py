import os

import pytest
from fastapi import HTTPException

from apps.api.auth import require_admin
from apps.api.paths import resolve_ingest_path, stage_uploaded_files


def test_missing_or_wrong_bearer_is_unauthorized(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    with pytest.raises(HTTPException) as missing:
        require_admin(None)
    assert missing.value.status_code == 401
    assert missing.value.detail["error"] == "unauthorized"

    with pytest.raises(HTTPException) as wrong:
        require_admin("Bearer nope")
    assert wrong.value.status_code == 401
    assert wrong.value.detail["error"] == "unauthorized"


def test_prefix_lookalike_path_is_forbidden(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    evil = tmp_path / "allowed-evil"
    allowed.mkdir()
    evil.mkdir()
    monkeypatch.setenv("ALLOWED_INGEST_ROOT", str(allowed))
    with pytest.raises(HTTPException) as exc:
        resolve_ingest_path(str(evil))
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "forbidden_path"


def test_symlink_inside_root_pointing_outside_is_forbidden(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    link = allowed / "escape"
    link.symlink_to(outside)
    monkeypatch.setenv("ALLOWED_INGEST_ROOT", str(allowed))
    with pytest.raises(HTTPException) as exc:
        resolve_ingest_path(str(link))
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "forbidden_path"


def test_quoted_file_url_and_home_paths_resolve(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    folder = allowed / "docs"
    folder.mkdir(parents=True)
    monkeypatch.setenv("ALLOWED_INGEST_ROOT", str(allowed))
    assert resolve_ingest_path(f'"{folder}"') == folder.resolve()
    assert resolve_ingest_path(f"'{folder}'") == folder.resolve()
    assert resolve_ingest_path(f"  {folder}  ") == folder.resolve()
    assert resolve_ingest_path(f"file://{folder}") == folder.resolve()


def test_missing_folder_is_bad_folder(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("ALLOWED_INGEST_ROOT", str(allowed))
    with pytest.raises(HTTPException) as exc:
        resolve_ingest_path(str(allowed / "missing"))
    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "bad_folder"


def test_stage_uploaded_files_writes_under_root(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("ALLOWED_INGEST_ROOT", str(allowed))
    dest = stage_uploaded_files([("note.txt", b"timeline milestone")])
    assert dest.is_dir()
    assert dest.parent == allowed.resolve()
    assert (dest / "note.txt").read_bytes() == b"timeline milestone"


def test_stage_uploaded_files_accepts_any_extension(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("ALLOWED_INGEST_ROOT", str(allowed))
    dest = stage_uploaded_files(
        [
            ("brief.md", b"# timeline"),
            ("data.json", b'{"budget": 1}'),
            ("LICENSE", b"permission notice"),
        ]
    )
    assert (dest / "brief.md").read_bytes() == b"# timeline"
    assert (dest / "data.json").read_bytes() == b'{"budget": 1}'
    assert (dest / "LICENSE").read_bytes() == b"permission notice"


def test_stage_uploaded_files_uses_basename_for_nested_name(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("ALLOWED_INGEST_ROOT", str(allowed))
    dest = stage_uploaded_files([("../evil.txt", b"nope")])
    assert (dest / "evil.txt").read_bytes() == b"nope"


def test_stage_uploaded_files_keeps_duplicate_names(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("ALLOWED_INGEST_ROOT", str(allowed))
    dest = stage_uploaded_files([("note.txt", b"first"), ("note.txt", b"second")])
    assert (dest / "note.txt").read_bytes() == b"first"
    assert (dest / "note_2.txt").read_bytes() == b"second"
