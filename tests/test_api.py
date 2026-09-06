import pytest
from fastapi.testclient import TestClient

from apps.api.main import ApiContext, create_app
from apps.api.routes import execute_job
from backend.agent_builder.formatter import format_job
from backend.rag_engine.retriever import get_state, reset_state
from backend.rag_engine.types import Chunk, ChunkMetadata
from tests.fake_embedder import FakeEmbedder

AUTH = {"Authorization": "Bearer secret"}


@pytest.fixture
def root(tmp_path, monkeypatch):
    reset_state()
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    monkeypatch.setenv("ALLOWED_INGEST_ROOT", str(allowed))
    yield allowed
    reset_state()


def _client(ctx: ApiContext | None = None) -> TestClient:
    return TestClient(create_app(ctx or ApiContext(embedder=FakeEmbedder())))


def _chunk(chunk_id: str, content: str, type_: str = "txt", category: str = "pm") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        metadata=ChunkMetadata(
            document_id="doc_1",
            source="budget.csv" if type_ == "csv" else "charter.pdf",
            type=type_,
            category=category,
            auto_category=category,
            page=1 if type_ == "pdf" else None,
            row_start=1 if type_ == "csv" else None,
            row_end=2 if type_ == "csv" else None,
            relevance=0.9,
            cross_category=False,
        ),
    )


def _agent(name: str, finding: dict, status: str = "done", error=None):
    def run(state):
        if status == "failed":
            raise RuntimeError(error or "boom")
        return {
            "findings": [finding],
            "timeline_events": [
                {
                    "agent": name,
                    "status": status,
                    "chunks_retrieved": len(finding.get("chunks") or []),
                    "primary_count": 1,
                    "used_live_web": False,
                    "error": error,
                }
            ],
            "warnings": [],
        }

    return run


def _finding(agent: str, chunk: Chunk, used: list[str] | None = None) -> dict:
    return {
        "agent": agent,
        "title": agent,
        "summary": "summary",
        "body": "body",
        "key_points": ["point"],
        "used_chunk_ids": used if used is not None else [chunk.chunk_id],
        "chunks": [chunk],
        "citation_ids": [],
    }


def _ingest(client: TestClient, folder, name="note.txt", text="timeline milestone budget revenue"):
    (folder / name).write_text(text)
    response = client.post(
        "/admin/ingest",
        json={"folder_path": str(folder), "category": "financial"},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    return response


def test_empty_kb_query_is_409(root):
    client = _client()
    response = client.post("/query", json={"query": "hello"})
    assert response.status_code == 409
    assert response.json()["error"] == "kb_empty"
    assert response.json()["message"] == "Knowledge base not loaded — ask admin."


def test_empty_question_is_400(root):
    client = _client()
    _ingest(client, root)
    response = client.post("/query", json={"query": "   "})
    assert response.status_code == 400
    assert response.json()["error"] == "empty_query"


def test_admin_missing_token_is_401(root):
    client = _client()
    response = client.get("/admin/documents")
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_path_outside_root_is_403(root, tmp_path):
    client = _client()
    outside = tmp_path / "outside"
    outside.mkdir()
    response = client.post("/admin/ingest", json={"folder_path": str(outside)}, headers=AUTH)
    assert response.status_code == 403
    assert response.json()["error"] == "forbidden_path"


def test_empty_folder_ingest_is_400_and_does_not_swap(root):
    client = _client()
    empty = root / "empty"
    empty.mkdir()
    response = client.post("/admin/ingest", json={"folder_path": str(empty)}, headers=AUTH)
    assert response.status_code == 400
    assert response.json()["error"] == "bad_folder"
    kb = client.get("/kb").json()
    assert kb["loaded"] is False
    assert kb["document_count"] == 0


def test_ingest_unexpected_error_returns_json_envelope(root, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("embedder exploded")

    monkeypatch.setattr("apps.api.routes.ingest", boom)
    client = _client()
    (root / "note.txt").write_text("timeline milestone")
    response = client.post("/admin/ingest", json={"folder_path": str(root)}, headers=AUTH)
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "ingest_failed"
    assert "embedder exploded" in body["message"]


def test_multipart_ingest_loads_kb(root):
    client = _client()
    response = client.post(
        "/admin/ingest",
        files=[("files", ("note.txt", b"timeline milestone budget revenue", "text/plain"))],
        data={"category": "financial"},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["documents"]
    assert body["documents"][0]["source"] == "note.txt"
    kb = client.get("/kb").json()
    assert kb["loaded"] is True
    assert kb["document_count"] == 1


def test_multipart_ingest_no_files_is_400(root):
    client = _client()
    response = client.post(
        "/admin/ingest",
        files=[("files", ("", b"", "application/octet-stream"))],
        data={"category": "financial"},
        headers=AUTH,
    )
    assert response.status_code == 400
    assert response.json()["error"] == "bad_folder"
    assert client.get("/kb").json()["loaded"] is False


def test_multipart_ingest_rejects_path_in_filename(root):
    client = _client()
    response = client.post(
        "/admin/ingest",
        files=[("files", ("../evil.txt", b"timeline milestone", "text/plain"))],
        headers=AUTH,
    )
    assert response.status_code == 400
    assert response.json()["error"] == "bad_folder"


def test_multipart_both_folder_and_files_is_400(root):
    (root / "note.txt").write_text("timeline milestone budget revenue")
    client = _client()
    response = client.post(
        "/admin/ingest",
        files=[("files", ("upload.txt", b"timeline milestone budget revenue", "text/plain"))],
        data={"folder_path": str(root)},
        headers=AUTH,
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "choose_one"
    assert "not both" in body["message"]
    assert client.get("/kb").json()["loaded"] is False


def test_multipart_folder_path_only_ingests(root):
    (root / "note.txt").write_text("timeline milestone budget revenue")
    client = _client()
    response = client.post(
        "/admin/ingest",
        files=[("files", ("", b"", "application/octet-stream"))],
        data={"folder_path": str(root), "category": "financial"},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    assert response.json()["documents"]
    assert client.get("/kb").json()["loaded"] is True


def test_admin_documents_empty_kb(root):
    client = _client()
    response = client.get("/admin/documents", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"documents": []}


def test_kb_has_no_path_or_filenames(root):
    client = _client()
    payload = client.get("/kb").json()
    assert set(payload) == {"loaded", "document_count"}
    assert payload["loaded"] is False


def test_unknown_job_is_404(root):
    client = _client()
    response = client.get("/status/job_missing")
    assert response.status_code == 404
    assert response.json()["error"] == "job_not_found"


def test_pdf_not_ready_is_404(root):
    client = _client()
    response = client.get("/report/job_missing/pdf")
    assert response.status_code == 404
    assert response.json()["error"] in {"pdf_not_ready", "job_not_found"}


def test_execute_job_does_not_mark_completed_until_result_exists(root, monkeypatch):
    chunk = _chunk("chk_1", "timeline milestone")
    ctx = ApiContext(
        embedder=FakeEmbedder(),
        chat_sync=lambda messages, **kwargs: '{"agents": ["pm"]}',
        agents={"pm": _agent("pm", _finding("pm", chunk))},
    )
    client = _client(ctx)
    _ingest(client, root)
    job = ctx.registry.create("timeline?")
    job["handle"] = get_state().handle
    seen: list[str] = []

    def spy(*args, **kwargs):
        seen.append(job["status"])
        assert job.get("result") is None
        return format_job(*args, **kwargs)

    monkeypatch.setattr("apps.api.routes.format_job", spy)
    execute_job(ctx, job)
    assert seen == ["formatting"]
    assert job["status"] == "completed"
    assert job["result"] is not None


def test_one_agent_failure_still_merges(root):
    chunk = _chunk("chk_1", "budget text about revenue")
    ctx = ApiContext(
        embedder=FakeEmbedder(),
        chat_sync=lambda messages, **kwargs: '{"agents": ["financial", "pm"]}',
        agents={
            "financial": _agent("financial", _finding("financial", chunk)),
            "pm": _agent("pm", _finding("pm", chunk), status="failed", error="boom"),
        },
    )
    client = _client(ctx)
    _ingest(client, root)
    job_id = client.post("/query", json={"query": "timeline and budget?"}).json()["job_id"]
    status = client.get(f"/status/{job_id}").json()
    assert status["status"] == "completed"
    assert status["result"] is not None
    timeline = {row["agent"]: row["status"] for row in status["timeline"]}
    assert timeline["pm"] == "failed"
    assert timeline["financial"] == "done"


def test_invented_and_unhanded_chunk_ids_are_dropped(root):
    chunk = _chunk("chk_real", "alpha text about budget")
    ctx = ApiContext(
        embedder=FakeEmbedder(),
        chat_sync=lambda messages, **kwargs: '{"agents": ["pm"]}',
        agents={"pm": _agent("pm", _finding("pm", chunk, used=["chk_real", "chk_invented"]))},
    )
    client = _client(ctx)
    _ingest(client, root)
    job_id = client.post("/query", json={"query": "timeline?"}).json()["job_id"]
    result = client.get(f"/status/{job_id}").json()["result"]
    assert [item["id"] for item in result["citations"]] == ["c1"]
    assert result["warnings"]
    assert client.get(f"/status/{job_id}").json()["status"] == "completed"


def test_two_agents_one_chunk_share_citation(root):
    shared = _chunk("chk_budget", "region,quarter,revenue\neast,Q1,10", type_="csv", category="financial")
    ctx = ApiContext(
        embedder=FakeEmbedder(),
        chat_sync=lambda messages, **kwargs: '{"agents": ["pm", "financial"]}',
        agents={
            "financial": _agent("financial", _finding("financial", shared)),
            "pm": _agent("pm", _finding("pm", shared)),
        },
    )
    client = _client(ctx)
    _ingest(client, root)
    job_id = client.post("/query", json={"query": "timeline and budget?"}).json()["job_id"]
    result = client.get(f"/status/{job_id}").json()["result"]
    assert len(result["citations"]) == 1
    assert result["citations"][0]["id"] == "c1"
    assert result["answer"]["sections"][0]["citation_ids"] == ["c1"]
    assert result["answer"]["sections"][1]["citation_ids"] == ["c1"]


def test_quotes_are_substrings_and_csv_includes_data_row(root):
    csv_chunk = _chunk(
        "chk_csv",
        "region,quarter,revenue,budget\neast,Q1,10,12\nwest,Q1,20,18",
        type_="csv",
        category="financial",
    )
    ctx = ApiContext(
        embedder=FakeEmbedder(),
        chat_sync=lambda messages, **kwargs: '{"agents": ["financial"]}',
        agents={"financial": _agent("financial", _finding("financial", csv_chunk))},
    )
    client = _client(ctx)
    _ingest(client, root)
    job_id = client.post("/query", json={"query": "budget?"}).json()["job_id"]
    citation = client.get(f"/status/{job_id}").json()["result"]["citations"][0]
    assert citation["quote"] in csv_chunk.content
    assert "region,quarter,revenue,budget" in citation["quote"]
    assert "east,Q1,10,12" in citation["quote"]


def test_report_pdf_when_available(root):
    chunk = _chunk("chk_1", "timeline milestone")
    ctx = ApiContext(
        embedder=FakeEmbedder(),
        chat_sync=lambda messages, **kwargs: '{"agents": ["pm"]}',
        agents={"pm": _agent("pm", _finding("pm", chunk))},
    )
    client = _client(ctx)
    _ingest(client, root)
    job_id = client.post("/query", json={"query": "timeline?"}).json()["job_id"]
    status = client.get(f"/status/{job_id}").json()
    assert status["result"]["pdf_available"] is True
    pdf = client.get(f"/report/{job_id}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")
    assert 'attachment; filename="pactlify-' in pdf.headers.get("content-disposition", "")


def test_failed_job_has_error_and_null_result(root):
    ctx = ApiContext(
        embedder=FakeEmbedder(),
        chat_sync=lambda messages, **kwargs: '{"agents": ["pm"]}',
        agents={"pm": _agent("pm", _finding("pm", _chunk("chk_1", "x")), status="failed", error="down")},
    )
    client = _client(ctx)
    _ingest(client, root)
    job_id = client.post("/query", json={"query": "timeline?"}).json()["job_id"]
    status = client.get(f"/status/{job_id}").json()
    assert status["status"] == "failed"
    assert status["error"]
    assert status["result"] is None


def test_patch_null_unmarks_and_leaves_auto_category(root):
    client = _client()
    _ingest(client, root)
    docs = client.get("/admin/documents", headers=AUTH).json()["documents"]
    doc_id = docs[0]["document_id"]
    auto = docs[0]["auto_category"]
    response = client.patch(f"/admin/documents/{doc_id}", json={"category": None}, headers=AUTH)
    assert response.status_code == 200
    document = response.json()["document"]
    assert document["category"] == "uncategorized"
    assert document["overridden"] is True
    assert document["auto_category"] == auto


def test_kb_and_admin_status_loaded_match(root):
    client = _client()
    assert client.get("/kb").json()["loaded"] == client.get("/admin/status", headers=AUTH).json()["loaded"]
    _ingest(client, root)
    kb = client.get("/kb").json()
    admin = client.get("/admin/status", headers=AUTH).json()
    assert kb["loaded"] is True
    assert kb["loaded"] == admin["loaded"]
    assert kb["document_count"] == admin["document_count"]
    assert "last_folder" not in kb


def test_combined_spa_serves_index_without_hiding_api(root, tmp_path, monkeypatch):
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("<html>Pactlify UI</html>", encoding="utf-8")
    assets = ui / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")
    monkeypatch.setenv("STATIC_DIR", str(ui))
    client = _client()
    home = client.get("/")
    assert home.status_code == 200
    assert "Pactlify UI" in home.text
    client_page = client.get("/client")
    assert client_page.status_code == 200
    assert "Pactlify UI" in client_page.text
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "console.log" in asset.text
    kb = client.get("/kb")
    assert kb.status_code == 200
    assert kb.json()["loaded"] is False


def test_openapi_includes_wire_field_names(root):
    spec = _client().get("/openapi.json").json()
    blob = str(spec)
    for needle in (
        "document_id",
        "source",
        "category",
        "pdf_available",
        "queued",
        "routing",
        "running",
        "merging",
        "formatting",
        "completed",
        "failed",
    ):
        assert needle in blob, needle
