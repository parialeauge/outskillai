from __future__ import annotations

import os

from fastapi import HTTPException


def require_admin(authorization: str | None, *, token: str | None = None) -> None:
    expected = token if token is not None else os.getenv("ADMIN_TOKEN", "")
    header = (authorization or "").strip()
    scheme, _, value = header.partition(" ")
    if not expected or scheme.lower() != "bearer" or value != expected:
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "Missing or wrong admin token."},
        )
