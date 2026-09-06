from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_FILE)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from apps.api.routes import ApiContext, build_router

__all__ = ["ApiContext", "app", "create_app"]


def _bundled_ui() -> str | None:
    root = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if (root / "index.html").is_file():
        return str(root)
    return None


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGIN", "http://localhost:5173")
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or ["http://localhost:5173"]


def _mount_ui(application: FastAPI, static_dir: str | None) -> None:
    if not static_dir:
        return
    root = Path(static_dir).resolve()
    index = root / "index.html"
    if not root.is_dir() or not index.is_file():
        return
    assets = root / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @application.get("/")
    async def spa_root():
        return FileResponse(index)

    @application.get("/{full_path:path}")
    async def spa(full_path: str):
        candidate = (root / full_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return FileResponse(index)
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


def create_app(context: ApiContext | None = None) -> FastAPI:
    ctx = context or ApiContext()
    application = FastAPI(title="Pactlify")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @application.exception_handler(HTTPException)
    async def http_error(_request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            return JSONResponse(status_code=exc.status_code, content=detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "error", "message": str(detail)},
        )

    application.include_router(build_router(ctx))
    _mount_ui(application, os.getenv("STATIC_DIR") or _bundled_ui())
    application.state.context = ctx
    return application


app = create_app()
