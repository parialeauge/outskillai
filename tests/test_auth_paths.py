import os

import pytest
from fastapi import HTTPException

from apps.api.auth import require_admin
from apps.api.paths import resolve_ingest_path


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


def test_missing_folder_is_bad_folder(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("ALLOWED_INGEST_ROOT", str(allowed))
    with pytest.raises(HTTPException) as exc:
        resolve_ingest_path(str(allowed / "missing"))
    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "bad_folder"
