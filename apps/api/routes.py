from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from apps.api.auth import require_admin
from apps.api.paths import resolve_ingest_path
from apps.api.session_registry import JobRegistry
from packages.agent_builder.formatter import format_job
from packages.agent_builder.graph import build_graph, run_job
from packages.agent_builder.pdf_generator import safe_render
from packages.rag_engine import IngestRejected, ingest, list_documents, set_category
from packages.rag_engine.retriever import get_state

KB_EMPTY_MESSAGE = "Knowledge base not loaded — ask admin."
PATCH_CATEGORIES = {"financial", "pm", "capex", "policy"}


@dataclass
class ApiContext:
    registry: JobRegistry = field(default_factory=JobRegistry)
    embedder: Any = None
    chat_sync: Any = None
    agents: dict | None = None


class IngestRequest(BaseModel):
    folder_path: str
    category: str | None = None


class QueryRequest(BaseModel):
    query: str


class PatchDocumentRequest(BaseModel):
    category: str | None = None


JobStatusName = Literal["queued", "routing", "running", "merging", "formatting", "completed", "failed"]


class KbInfo(BaseModel):
    loaded: bool
    document_count: int


class DocumentOut(BaseModel):
    document_id: str
    source: str
    type: str
    chunk_count: int
    auto_category: str
    category: str
    overridden: bool = False


class DocumentsOut(BaseModel):
    documents: list[DocumentOut]


class CitationOut(BaseModel):
    id: str
    source: str
    type: str
    category: str
    page: int | None = None
    row_start: int | None = None
    row_end: int | None = None
    cross_category: bool = False
    quote: str


class SectionOut(BaseModel):
    agent: str
    title: str
    body: str
    key_points: list[str]
    citation_ids: list[str]


class AnswerOut(BaseModel):
    summary: str
    sections: list[SectionOut]


class ResultEnvelope(BaseModel):
    job_id: str
    query: str
    activated_agents: list[str]
    answer: AnswerOut
    citations: list[CitationOut]
    warnings: list[str]
    pdf_available: bool


class TimelineEventOut(BaseModel):
    agent: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    chunks_retrieved: int | None = None
    primary_count: int | None = None
    used_live_web: bool | None = None
    error: str | None = None


class JobStatusPayload(BaseModel):
    job_id: str
    status: JobStatusName
    query: str
    created_at: str
    activated_agents: list[str]
    timeline: list[TimelineEventOut]
    warnings: list[str]
    error: str | None = None
    result: ResultEnvelope | None = None


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    def admin(authorization: str | None) -> None:
        require_admin(authorization)

    @router.get("/kb", response_model=KbInfo)
    def kb():
        state = get_state()
        return {"loaded": state.handle is not None, "document_count": len(state.documents)}

    @router.get("/admin/status")
    def admin_status(authorization: str | None = Header(default=None)):
        admin(authorization)
        state = get_state()
        return {
            "loaded": state.handle is not None,
            "last_folder": state.last_folder,
            "document_count": len(state.documents),
            "chunk_count": state.chunk_count,
            "failed_files": [item.model_dump() for item in state.failed_files],
            "failed_urls": [item.model_dump() for item in state.failed_urls],
        }

    @router.get("/admin/documents", response_model=DocumentsOut)
    def admin_documents(authorization: str | None = Header(default=None)):
        admin(authorization)
        return {"documents": [item.model_dump() for item in list_documents("shared")]}

    @router.post("/admin/ingest")
    async def admin_ingest(
        body: IngestRequest,
        authorization: str | None = Header(default=None),
    ):
        admin(authorization)
        if body.category == "uncategorized":
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_folder", "message": 'Stamping a folder "uncategorized" is not allowed.'},
            )
        path = resolve_ingest_path(body.folder_path)
        try:
            result = await asyncio.to_thread(_ingest, str(path), body.category, ctx.embedder)
        except IngestRejected as error:
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_folder", "message": str(error)},
            ) from error
        except Exception as error:  # noqa: BLE001 — surface embedder/loader crashes to the admin UI
            raise HTTPException(
                status_code=500,
                detail={"error": "ingest_failed", "message": str(error)},
            ) from error
        return result.model_dump()

    @router.patch("/admin/documents/{document_id}")
    def admin_patch(
        document_id: str,
        body: PatchDocumentRequest,
        authorization: str | None = Header(default=None),
    ):
        admin(authorization)
        if body.category is not None and body.category not in PATCH_CATEGORIES:
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_request", "message": "Invalid category."},
            )
        ok = set_category("shared", document_id, body.category)
        if not ok:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Unknown document id."},
            )
        documents = {item.document_id: item for item in list_documents("shared")}
        return {"ok": True, "document": documents[document_id].model_dump()}

    @router.post("/query")
    def post_query(body: QueryRequest, background: BackgroundTasks):
        query = (body.query or "").strip()
        if not query:
            raise HTTPException(
                status_code=400,
                detail={"error": "empty_query", "message": "Query must not be empty."},
            )
        if get_state().handle is None:
            raise HTTPException(
                status_code=409,
                detail={"error": "kb_empty", "message": KB_EMPTY_MESSAGE},
            )
        job = ctx.registry.create(query)
        job["handle"] = get_state().handle
        background.add_task(execute_job, ctx, job)
        return {"job_id": job["job_id"]}

    @router.get("/status/{job_id}", response_model=JobStatusPayload)
    def get_status(job_id: str):
        job = ctx.registry.get(job_id)
        return _public_job(job)

    @router.get("/report/{job_id}/pdf")
    def get_pdf(job_id: str):
        job = ctx.registry.get(job_id)
        result = job.get("result") or {}
        pdf = job.get("pdf_bytes")
        if job.get("status") != "completed" or not result.get("pdf_available") or not pdf:
            raise HTTPException(
                status_code=404,
                detail={"error": "pdf_not_ready", "message": "PDF is not available for this job."},
            )
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="pactlify-{job_id}.pdf"'},
        )

    return router


def execute_job(ctx: ApiContext, job: dict) -> None:
    handle = job.get("handle") or get_state().handle
    built = {"financial", "pm", "capex", "general"}
    graph = build_graph(built, agents=ctx.agents, chat_sync=ctx.chat_sync)

    def updater(status: str, **kwargs) -> None:
        job["status"] = status

    try:
        out = run_job(job["query"], handle, updater, built=built, graph=graph, chat_sync=ctx.chat_sync)
    except Exception as error:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = str(error)
        job["result"] = None
        return

    job["activated_agents"] = list(out.get("activated") or [])
    job["timeline"] = list(out.get("timeline_events") or [])
    warnings = list(out.get("warnings") or [])
    findings = list(out.get("merged_findings") or [])
    if not findings and (not job["timeline"] or all(event.get("status") == "failed" for event in job["timeline"])):
        job["status"] = "failed"
        job["error"] = next((event.get("error") for event in job["timeline"] if event.get("error")), "All agents failed")
        job["result"] = None
        job["warnings"] = warnings
        return

    if not job["activated_agents"]:
        job["activated_agents"] = [item.get("agent") for item in findings if item.get("agent")]

    handed = {item.get("agent"): item.get("chunks") or [] for item in findings}
    envelope = format_job(
        job["query"],
        job["activated_agents"],
        findings,
        handed,
        warnings,
        job_id=job["job_id"],
    )
    pdf, available, pdf_warnings = safe_render(envelope)
    envelope["warnings"] = list(envelope.get("warnings") or []) + pdf_warnings
    envelope["pdf_available"] = available
    job["result"] = envelope
    job["pdf_bytes"] = pdf
    job["warnings"] = envelope["warnings"]
    job["status"] = "completed"
    job["error"] = None


def _ingest(folder_path: str, stamp: str | None, embedder):
    kwargs: dict[str, Any] = {}
    if embedder is not None:
        kwargs["embedder"] = embedder
    return ingest(folder_path, stamp=stamp, **kwargs)


def _public_job(job: dict) -> dict:
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "query": job["query"],
        "created_at": job["created_at"],
        "activated_agents": job.get("activated_agents") or [],
        "timeline": job.get("timeline") or [],
        "warnings": job.get("warnings") or [],
        "error": job.get("error"),
        "result": job.get("result"),
    }
