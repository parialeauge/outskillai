from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.routes import ApiContext, build_router

__all__ = ["ApiContext", "app", "create_app"]


def create_app(context: ApiContext | None = None) -> FastAPI:
    ctx = context or ApiContext()
    application = FastAPI(title="Pactlify")
    origin = os.getenv("CORS_ORIGIN", "http://localhost:5173")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[origin],
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
    application.state.context = ctx
    return application


app = create_app()
