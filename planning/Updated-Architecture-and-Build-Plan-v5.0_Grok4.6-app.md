# Pactlify Backend Implementation Plan (v5.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Pactlify backend: `rag_engine` (folder ingest + category-preferring retrieval), `agent_builder` (parent router + specialists + formatter + minimal PDF), and thin FastAPI glue with an in-memory job registry.

**Architecture:** FastAPI is routes, CORS, auth, and in-process state only. `rag_engine` owns files, chunking, local embeddings, LanceDB, and `ingest` / `retrieve` / `clear` / `list_documents` / `set_category`. `agent_builder` never parses files; it calls `retrieve()`, OpenRouter, Tavily/NewsAPI, then merge → formatter → PDF. Both packages import in-process — no HTTP between them. Single worker: `uvicorn apps.api.main:app --workers 1`.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, LanceDB (temp dir, not `EphemeralClient()`), sentence-transformers `all-MiniLM-L6-v2`, LangGraph, OpenRouter, Tavily, NewsAPI, LangSmith, PyMuPDF, pandas, WeasyPrint (ReportLab fallback), pytest.

**Source of truth:** `outskillai/planning/Updated-Architecture-and-Build-Plan-v4.0_Opus5.md`. This file is the backend-only implementation plan derived from it.

**Companion:** Frontend plan is `outskillai/planning/Updated-Architecture-and-Build-Plan-v4.0_Opus5-ui.md`. Do not implement React in this plan. Produce the §8 wire contract the UI consumes. Save real formatter output to `frontend/src/fixtures/` as soon as Task 16 runs so the UI plan can consume it.

## Global Constraints

- Product name: **Pactlify**. Backend does not render UI; PDF title is **Pactlify**.
- Two modules only: `rag_engine` and `agent_builder`. FastAPI is thin glue, not a third product.
- Vector DB: LanceDB, per-process temp directory, discarded on exit. `lancedb.connect(tempfile.mkdtemp(prefix="outskill-kb-"))`. Never `EphemeralClient()`.
- Process model: **Single worker.** `uvicorn apps.api.main:app --workers 1`, no `--reload`.
- Folder scan: **top-level files only — subdirectories are not scanned**. Types: `pdf`, `csv`, `txt`, `urls.txt`.
- Categories: `financial` / `pm` / `capex` / `policy` / `uncategorized`. Never store NULL category; store the literal `'uncategorized'`.
- Python ingest call site is `ingest(folder_path, stamp=None)` → **auto-detect**. `set_category(..., category=None)` → **unmark** to `'uncategorized'`. HTTP ingest still uses the field name `category`. Never pass the string `"uncategorized"` as an ingest stamp.
- Ingest stamp `"uncategorized"` is rejected `400 bad_folder`. Allowed stamps: `financial` | `pm` | `capex` | `policy`.
- Stamped batch: `category = stamp`, `auto_category = 'uncategorized'`, `overridden = true`. Classifier skipped.
- Retrieval: preference with flagged backfill. **Primary is category-matched only** — no `OR type = 'web'`.
- Live web keyed on `primary_count`, never `len(chunks)`. Financial / PM / CapEx: live web only if primary is empty. General: if primary `< GENERAL_THIN_PRIMARY` or `needs_current_info`.
- Reload is build-then-swap. Never `table.add()` onto the live table. Jobs capture the table handle at start.
- Citations derived by the formatter. Agents never mint citation ids. `quote` copied from chunk text.
- Admin endpoints: `Authorization: Bearer <ADMIN_TOKEN>`. Ingest paths: `Path.resolve(strict=True)` + `os.path.commonpath`, not `startswith`.
- Chat model: `OPENROUTER_MODEL` (default `openai/gpt-4o-mini`). If one external service fails, continue with what works.
- Blocking work off the event loop: `await asyncio.to_thread(...)` around every embed and every LanceDB search.
- Packaging: editable install via `outskillai/pyproject.toml`. No `sys.path` appends, no `PYTHONPATH` exports.
- Limits (all in `shared/config.py` or `pactlify_shared/config.py` if `shared` collides):


| Name                           | Value                                                      |
| ------------------------------ | ---------------------------------------------------------- |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 1000 / 200 chars                                           |
| `CSV_ROWS_PER_CHUNK`           | 10–50 rows, row-bounded                                    |
| `TOP_K`                        | 5                                                          |
| `MIN_PRIMARY`                  | 3                                                          |
| `GENERAL_THIN_PRIMARY`         | 2                                                          |
| `LLM_TIMEOUT`                  | 30s (one retry on connection error only, never on timeout) |
| `AGENT_TIMEOUT`                | 60s                                                        |
| `JOB_TIMEOUT`                  | **300s**                                                   |
| `URL_FETCH_TIMEOUT`            | 10s                                                        |
| `URL_FETCH_CONCURRENCY`        | 5                                                          |
| `MAX_FILES`                    | 40                                                         |
| `MAX_FILE_MB`                  | 25                                                         |
| `MAX_URLS`                     | 20                                                         |
| `MAX_URL_BYTES`                | 5 MB                                                       |
| `JOB_RETENTION`                | 50 jobs LRU / 30 min TTL; never evict a running job        |


---



## Out of scope (this plan)

- React UI, mosaic/pastel tokens, `documentStore`, fixture-driven screens — UI plan.
- Browser file-drop ingest, row-level retag UI, real login, durable LanceDB, saved overrides, `categories.txt`, recursive folder ingest, `clear()` HTTP route, `POST /query` rate limiting, re-classify-on-demand, custom `resource`/`out` templates as the primary renderer.
- ChromaDB. Do not add it.

---



## File map

```
outskillai/
├── pyproject.toml
├── .env.example
├── README.md                         # run command: uvicorn --workers 1
├── apps/api/
│   ├── __init__.py
│   ├── main.py                       # FastAPI app, CORS, lifespan
│   ├── routes.py                     # all §8 endpoints
│   ├── auth.py                       # ADMIN_TOKEN Bearer check
│   ├── paths.py                      # ALLOWED_INGEST_ROOT resolve+commonpath
│   └── session_registry.py           # active KB pointer + jobs + JOB_RETENTION
├── packages/
│   ├── rag_engine/
│   │   ├── __init__.py               # re-export public API
│   │   ├── types.py                  # Chunk, DocumentInfo, IngestResult, RetrieveResult
│   │   ├── ingestion.py              # flat scan, caps, PDF/CSV/TXT/urls.txt
│   │   ├── chunker.py
│   │   ├── embeddings.py
│   │   ├── classifier.py
│   │   ├── vectorstore.py
│   │   └── retriever.py              # ingest / retrieve / clear / list_documents / set_category
│   └── agent_builder/
│       ├── __init__.py
│       ├── state.py
│       ├── parent_agent.py
│       ├── financial_agent.py
│       ├── pm_agent.py
│       ├── capex_agent.py
│       ├── general_agent.py
│       ├── graph.py
│       ├── formatter.py
│       └── pdf_generator.py
├── shared/                           # rename to pactlify_shared if install collides
│   ├── __init__.py
│   ├── config.py
│   └── llm.py
├── tests/
│   ├── fake_embedder.py
│   ├── test_chunker.py
│   ├── test_rag_engine.py
│   ├── test_retriever.py
│   ├── test_lifecycle.py
│   ├── test_formatter.py
│   ├── test_agents.py
│   └── test_api.py
├── sample_data/                      # flat folder; mixed PDF required
├── resource/                         # later: templates (loader only)
└── out/                              # later: generated reports
```

---



## Public package interface (locked)

```python
def ingest(folder_path: str, stamp: str | None = None) -> IngestResult:
    """stamp=None auto-classifies. stamp in {financial, pm, capex, policy} stamps the batch."""

def retrieve(
    knowledge_base_id: str,
    query: str,
    top_k: int = TOP_K,
    category: str | list[str] | None = None,
    source_type: str | list[str] | None = None,
    handle: "TableHandle | None" = None,
) -> RetrieveResult:
    """category is a preference, not an exclusion. Read primary_count, not len(chunks).
    If handle is provided (a running job's captured table), search that table even if ingest has swapped."""

def clear(knowledge_base_id: str) -> bool:
    """Drops the active table. No HTTP route in this slice."""

def list_documents(knowledge_base_id: str) -> list[DocumentInfo]:
    """Bare Python list. HTTP wraps as {\"documents\": [...]}."""

def set_category(knowledge_base_id: str, document_id: str, category: str | None) -> bool:
    """category=None unmarks every chunk to 'uncategorized' and sets overridden=True. Leaves auto_category."""
```

HTTP still uses `category` on `POST /admin/ingest`. The Python ingest parameter is `stamp=` so `None` cannot be confused with `set_category(..., category=None)`.

`RetrieveResult`: `chunks: list[Chunk]` (primary first, then backfill), `primary_count: int`.

`Chunk`: `chunk_id`, `content`, `metadata.document_id`, `metadata.source`, `metadata.type` (`pdf`/`csv`/`txt`/`web`), `metadata.category`, `metadata.auto_category`, `metadata.page`, `metadata.row_start`, `metadata.row_end`, `metadata.relevance` (cosine similarity in `[0, 1]`, higher-is-better — convert LanceDB `_distance` once in `vectorstore.py`), `metadata.cross_category`.

`DocumentInfo`: `document_id`, `source`, `type`, `chunk_count`, `auto_category`, `category`, `overridden: bool`.

`IngestResult`: `knowledge_base_id` (`"shared"`), `documents`, `failed_files: list[{name, reason}]`, `failed_urls: list[{url, reason}]`, `chunk_count`.

`knowledge_base_id` is always `"shared"`.

---



## Wire contract this plan must produce

Base origin is whatever the UI's `VITE_API_BASE_URL` points at (default `http://localhost:8000`). JSON `Content-Type: application/json` except PDF. Shared 4xx body: `{ "error": "error_code", "message": "human-readable string" }`. CORS must allow `Authorization` from the React origin.


| Endpoint                      | Auth   | Success                                                                                 | Errors                                      |
| ----------------------------- | ------ | --------------------------------------------------------------------------------------- | ------------------------------------------- |
| `GET /kb`                     | none   | `{ loaded, document_count }` — no path, no filenames                                    | —                                           |
| `GET /admin/status`           | Bearer | last folder, counts, `failed_*`                                                         | 401                                         |
| `GET /admin/documents`        | Bearer | `{ "documents": DocumentInfo[] }`; empty KB is `200` with `[]`, not 404                 | 401                                         |
| `POST /admin/ingest`          | Bearer | `IngestResult`; omit/`null` `category` = auto-detect                                    | 400 `bad_folder`, 401, 403 `forbidden_path` |
| `PATCH /admin/documents/{id}` | Bearer | `{ ok, document }` — **implemented even though UI does not call it**                    | 400, 401, 404                               |
| `POST /query`                 | none   | `{ "job_id" }`                                                                          | 400 `empty_query`, 409 `kb_empty`           |
| `GET /status/{job_id}`        | none   | §7.2 payload                                                                            | 404 `job_not_found`                         |
| `GET /report/{job_id}/pdf`    | none   | `application/pdf` + `Content-Disposition: attachment; filename="pactlify-{job_id}.pdf"` | 404 `pdf_not_ready`                         |


Job status enum (only vocabulary): `queued` | `routing` | `running` | `merging` | `formatting` | `completed` | `failed`.

Agent timeline status: `pending` | `retrieving` | `searching_web` | `synthesizing` | `done` | `failed`.

`result` is `null` until `status = "completed"`. `error` is `null` unless `status = "failed"`. Top-level `warnings[]` is the job warning log; copy the same list into `result.warnings[]` at format time.

Completed `result` shape:

```json
{
  "job_id": "string",
  "query": "string",
  "activated_agents": ["financial", "pm"],
  "answer": {
    "summary": "string",
    "sections": [
      {
        "agent": "pm",
        "title": "string",
        "body": "string",
        "key_points": ["string"],
        "citation_ids": ["c1"]
      }
    ]
  },
  "citations": [
    {
      "id": "c1",
      "source": "filename-or-url",
      "type": "pdf",
      "category": "pm",
      "page": 3,
      "row_start": null,
      "row_end": null,
      "cross_category": false,
      "quote": "string"
    }
  ],
  "warnings": [],
  "pdf_available": true
}
```

`POST /query` 409 message must be exactly: `Knowledge base not loaded — ask admin.`

Ingest is **synchronous**. Until the response returns, `GET /kb` still reflects the previous KB.

---



### Task 1: Packaging and editable install

**Files:**

- Create: `outskillai/pyproject.toml`
- Create: `outskillai/apps/__init__.py`, `outskillai/apps/api/__init__.py`
- Create: `outskillai/packages/__init__.py`, `outskillai/packages/rag_engine/__init__.py`, `outskillai/packages/agent_builder/__init__.py`
- Create: `outskillai/shared/__init__.py`
- Create: `outskillai/tests/__init__.py`
- Create: `outskillai/.env.example`
- Modify: `outskillai/README.md`

**Interfaces:**

- Consumes: nothing
- Produces: installable packages `apps`, `packages.rag_engine`, `packages.agent_builder`, `shared` via `pip install -e .` (or `uv pip install -e .`)

- [ ] **Step 1: Write** `pyproject.toml`

```toml
[project]
name = "pactlify"
version = "0.4.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi",
  "uvicorn[standard]",
  "lancedb",
  "sentence-transformers",
  "langgraph",
  "langchain-openai",
  "httpx",
  "pymupdf",
  "pandas",
  "python-dotenv",
  "pydantic",
  "tavily-python",
  "weasyprint",
  "reportlab",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "httpx"]

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["apps*", "packages*", "shared*"]
```

If `shared` collides with another distribution at install time, rename the directory and all imports to `pactlify_shared` in this task — not later.

- [ ] **Step 2: Write** `.env.example`

```
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4o-mini
TAVILY_API_KEY=
NEWSAPI_API_KEY=
LANGSMITH_API_KEY=
LANGCHAIN_API_KEY=
LANGCHAIN_TRACING_V2=false
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ADMIN_TOKEN=
ALLOWED_INGEST_ROOT=
```

- [ ] **Step 3: Install editable and prove imports**

```bash
cd outskillai
pip install -e ".[dev]"
python -c "from shared.config import TOP_K"
```

Expected: FAIL with `ModuleNotFoundError: shared.config` until Task 2 creates the module. After Task 2, this import succeeds. For this task, prove package discovery:

```bash
python -c "import apps.api, packages.rag_engine, packages.agent_builder, shared; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Document the run command in README.md**

Exact command: `uvicorn apps.api.main:app --workers 1`. No `--reload`. No `sys.path` hacks.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml apps packages shared tests .env.example README.md
git commit -m "chore: pin Pactlify editable packaging for apps, packages, and shared"
```

---



### Task 2: Limits module

**Files:**

- Create: `outskillai/shared/config.py`
- Test: `outskillai/tests/test_config.py`

**Interfaces:**

- Consumes: Task 1 packaging
- Produces: every §4.6 constant as a module-level name, imported by ingest, retrieve, agents, and the registry

- [ ] **Step 1: Write the failing test**

```python
from shared.config import (
    CHUNK_SIZE, CHUNK_OVERLAP, TOP_K, MIN_PRIMARY, GENERAL_THIN_PRIMARY,
    LLM_TIMEOUT, AGENT_TIMEOUT, JOB_TIMEOUT, URL_FETCH_TIMEOUT,
    URL_FETCH_CONCURRENCY, MAX_FILES, MAX_FILE_MB, MAX_URLS, MAX_URL_BYTES,
    JOB_RETENTION_MAX, JOB_RETENTION_TTL_SECONDS,
)

def test_job_timeout_covers_four_sequential_agents():
    assert JOB_TIMEOUT >= 4 * AGENT_TIMEOUT
    assert JOB_TIMEOUT == 300
    assert AGENT_TIMEOUT == 60
    assert MIN_PRIMARY == 3
    assert GENERAL_THIN_PRIMARY == 2
    assert GENERAL_THIN_PRIMARY != MIN_PRIMARY
    assert TOP_K == 5
    assert MAX_FILES == 40
    assert MAX_FILE_MB == 25
    assert MAX_URLS == 20
    assert MAX_URL_BYTES == 5 * 1024 * 1024
    assert JOB_RETENTION_MAX == 50
    assert JOB_RETENTION_TTL_SECONDS == 30 * 60
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_config.py::test_job_timeout_covers_four_sequential_agents -v
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Write** `shared/config.py` with those exact values plus `CHUNK_SIZE = 1000`, `CHUNK_OVERLAP = 200`, `CSV_ROWS_PER_CHUNK_MIN = 10`, `CSV_ROWS_PER_CHUNK_MAX = 50`, `LLM_TIMEOUT = 30`, `URL_FETCH_TIMEOUT = 10`, `URL_FETCH_CONCURRENCY = 5`.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_config.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shared/config.py tests/test_config.py
git commit -m "feat: centralize Pactlify pipeline limits in shared.config"
```

---



### Task 3: OpenRouter wrapper

**Files:**

- Create: `outskillai/shared/llm.py`
- Test: `outskillai/tests/test_llm.py`

**Interfaces:**

- Consumes: `LLM_TIMEOUT` from `shared.config`
- Produces: `async def chat(messages: list[dict], *, timeout: float = LLM_TIMEOUT, response_format: dict | None = None) -> str` and `def chat_sync(...)` for classifier/off-loop use. One retry on connection error only; never retry on timeout. Tracing via LangSmith env must never raise into the caller.

- [ ] **Step 1: Write the failing test** using `httpx.MockTransport` or a stubbed client: timeout is not retried; a single connection error is retried once; a second connection error raises.
- [ ] **Step 2: Run the test — expect FAIL** (`chat` not defined).
- [ ] **Step 3: Implement** `shared/llm.py` reading `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` (default `openai/gpt-4o-mini`) from env. Do not import this module from `rag_engine.vectorstore`.
- [ ] **Step 4: Run tests — expect PASS.**
- [ ] **Step 5: Commit** `feat: wrap OpenRouter with timeout and connection-only retry`

---



### Task 4: LanceDB pin and pre-filter proof

**Files:**

- Create: `outskillai/scripts/lancedb_prefilter_check.py`
- Create: `outskillai/tests/test_lancedb_prefilter.py`

**Interfaces:**

- Consumes: pinned `lancedb` from Task 1
- Produces: confirmed `connect(tmpdir)`, SQL `.where(...)`, and `prefilter=True` behaviour used by Task 11

- [ ] **Step 1: Pre-download embeddings (once, during setup)**

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

- [ ] **Step 2: REPL / script check against the pinned version**

```python
import tempfile, lancedb
db = lancedb.connect(tempfile.mkdtemp(prefix="outskill-kb-"))
```

Confirm: (1) connect works; (2) `.where("category = 'pm'")` returns expected rows; (3) write ~20 rows where only 3 have `category = 'pm'`, search `k=5`, and with `prefilter=True` the filter returns all 3. If it returns fewer or none, the predicate is post-filter — keep passing `prefilter=True` explicitly in `vectorstore.py`.

- [ ] **Step 3: Encode that third check as** `tests/test_lancedb_prefilter.py` so it stays in CI:

```python
def test_prefilter_returns_all_matching_rows_even_when_k_exceeds_matches(tmp_path):
    import lancedb
    db = lancedb.connect(tmp_path)
    rows = [{"id": i, "vector": [float(i)] * 8, "category": "pm" if i < 3 else "financial"} for i in range(20)]
    table = db.create_table("t", rows)
    hits = table.search([0.0] * 8).where("category = 'pm'", prefilter=True).limit(5).to_list()
    assert len(hits) == 3
```

- [ ] **Step 4: Commit** `test: lock LanceDB temp-dir connect and prefilter=True behaviour`

---



### Task 5: RAG domain types

**Files:**

- Create: `outskillai/packages/rag_engine/types.py`

**Interfaces:**

- Consumes: nothing
- Produces: dataclasses/Pydantic models `ChunkMetadata`, `Chunk`, `DocumentInfo`, `FailedFile`, `FailedUrl`, `IngestResult`, `RetrieveResult` with the fields listed in the public interface above. `category` is a `Literal` of the five strings; never `None`.

- [ ] **Step 1: Write** `types.py`**.** `FailedFile` is `{name: str, reason: str}`. `FailedUrl` is `{url: str, reason: str}`. `IngestResult.knowledge_base_id` defaults to `"shared"`.
- [ ] **Step 2: Commit** `feat: add rag_engine domain types`

---



### Task 6: Deterministic fake embedder

**Files:**

- Create: `outskillai/packages/rag_engine/embeddings.py`
- Create: `outskillai/tests/fake_embedder.py`
- Test: `outskillai/tests/test_embeddings.py`

**Interfaces:**

- Consumes: `EMBEDDING_MODEL` env (real path)
- Produces: `class Embedder` with `def encode(self, texts: list[str]) -> list[list[float]]`. Tests inject `FakeEmbedder` (hash-based unit vectors). Production uses `sentence-transformers/all-MiniLM-L6-v2`.

- [ ] **Step 1: Write** `FakeEmbedder` so identical strings get identical vectors and different strings are not orthogonal by accident (use a stable hash → 384-dim vector, L2-normalized).
- [ ] **Step 2: Write** `embeddings.py` with a constructor `Embedder(model: SentenceTransformer | FakeEmbedder)`. Real encode is CPU-bound; callers wrap with `asyncio.to_thread`.
- [ ] **Step 3: Test identical input → identical vector; different inputs → different vectors.**
- [ ] **Step 4: Commit** `feat: add embedder interface with hash-based fake for tests`

---



### Task 7: Per-type chunker

**Files:**

- Create: `outskillai/packages/rag_engine/chunker.py`
- Test: `outskillai/tests/test_chunker.py`

**Interfaces:**

- Consumes: `CHUNK_SIZE`, `CHUNK_OVERLAP`, `CSV_ROWS_PER_CHUNK_*` from config; `Chunk` from types
- Produces: `chunk_txt(text, *, document_id, source, type_)`, `chunk_pdf(pages: list[str], ...)`, `chunk_csv(header: str, rows: list[str], ...)`

Rules:

- `txt` / `web`: ~1000 characters, 200 overlap.
- `pdf`: ~1000 characters, 200 overlap, **never spanning a page boundary**. Every chunk's `metadata.page` is that page's 1-based index.
- `csv`: accumulate whole rows until the next row would exceed the budget; **never split mid-row**; repeat the CSV header in every chunk; set contiguous `row_start` / `row_end`.
- Duplicate suppression is **not** in this module; Task 8 hashes per document after chunking.

- [ ] **Step 1: Write failing tests**

```python
def test_pdf_chunk_does_not_span_pages():
    pages = ["A" * 800, "B" * 800]
    chunks = chunk_pdf(pages, document_id="d", source="a.pdf")
    assert all(set(c.content) <= {c.content[0], "\n"} or True for c in chunks)
    for c in chunks:
        assert "A" in c.content or "B" in c.content
        assert not ("A" in c.content and "B" in c.content)
        assert c.metadata.page in (1, 2)

def test_csv_never_splits_a_row_and_repeats_header():
    header = "region,quarter,revenue"
    rows = ["east,Q1,10", "west,Q1,20", "east,Q2,30"]
    chunks = chunk_csv(header, rows, document_id="d", source="a.csv")
    for c in chunks:
        assert c.content.splitlines()[0] == header
        assert c.metadata.row_start <= c.metadata.row_end
    # contiguous coverage of all rows
    covered = []
    for c in chunks:
        covered.extend(range(c.metadata.row_start, c.metadata.row_end + 1))
    assert covered == list(range(1, 4))
```

- [ ] **Step 2: Run tests — expect FAIL.**

- [ ] **Step 3: Implement** `chunker.py`**.**

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit** `feat: chunk txt, pdf, and csv with type-truthful metadata`

---



### Task 8: Flat folder scan, caps, and per-document dedupe

**Files:**

- Create: `outskillai/packages/rag_engine/ingestion.py` (scan + cap + load orchestration)
- Test: `outskillai/tests/test_ingest_scan.py`

**Interfaces:**

- Consumes: `MAX_FILES`, `MAX_FILE_MB`, `MAX_URLS`, `MAX_URL_BYTES`, `URL_FETCH_TIMEOUT`, `URL_FETCH_CONCURRENCY`
- Produces: `class IngestRejected(Exception)` with `code = "bad_folder"`; `scan_folder(path: Path) -> ScanResult` counting **top-level** `pdf`/`csv`/`txt`/`urls.txt` only; `dedupe_chunks_within_document(chunks: list[Chunk]) -> list[Chunk]` hashing `content` per `document_id`

Scan rules:

- Count candidates and `stat` sizes **before** any parsing.
- Over `MAX_FILES` → raise `IngestRejected` (`bad_folder`), no swap. Message includes the count.
- Folder exists but only subdirectories, no top-level ingestable files → `IngestRejected`. Message must say the scan is flat so it does not read as "your PDFs are broken."
- Missing path / not a directory → `IngestRejected`.
- File over `MAX_FILE_MB` → skip into `failed_files` with the size, continue.
- Dedupe: identical content **inside one document** collapses to one chunk. Identical content in **two documents** stays two chunks.

- [ ] **Step 1: Write failing tests** for over-`MAX_FILES`, subdirectory-only folder, oversized file skip, intra-document collapse, cross-document keep.
- [ ] **Step 2: Implement scan +** `dedupe_chunks_within_document`**.**
- [ ] **Step 3: Run tests — expect PASS.**
- [ ] **Step 4: Commit** `feat: scan folders flat with ingest caps and per-document chunk dedupe`

---



### Task 9: File and URL loaders

**Files:**

- Modify: `outskillai/packages/rag_engine/ingestion.py`
- Test: `outskillai/tests/test_loaders.py`

**Interfaces:**

- Consumes: Task 7 chunker, Task 8 scan
- Produces: `load_pdf`, `load_csv`, `load_txt`, `load_urls_txt` returning chunks plus failed entries

Loader rules:

- PDF via PyMuPDF.
- CSV via pandas; pass header + row strings into `chunk_csv`.
- TXT / CSV: decode UTF-8; on failure retry `latin-1`; only then `failed_files`.
- `urls.txt`: at most `MAX_URLS` entries (extras → `failed_urls`); 10s timeout; at most 5 concurrent; abort past `MAX_URL_BYTES`; skip non-HTML/non-text `Content-Type`; type `web`.
- Unreadable file → skip, list in `failed_files`, continue.

- [ ] **Step 1: Write failing tests** using temp files: latin-1 CSV succeeds; `urls.txt` over `MAX_URLS` lists extras; a response over `MAX_URL_BYTES` and a `application/pdf` Content-Type each land in `failed_urls` with **distinct** reasons.
- [ ] **Step 2: Implement loaders.** URL fetch must be skip-on-error; a hang is a timeout, not a stalled ingest.
- [ ] **Step 3: Run tests — expect PASS.**
- [ ] **Step 4: Commit** `feat: load pdf, csv, txt, and urls.txt with skip-and-list failures`

---



### Task 10: Two-level classifier

**Files:**

- Create: `outskillai/packages/rag_engine/classifier.py`
- Test: `outskillai/tests/test_classifier.py`

**Interfaces:**

- Consumes: `shared.llm.chat_sync` (doc-level), keyword lists
- Produces: `classify_document(text: str) -> Literal['financial','pm','capex','uncategorized']`; `classify_chunk(text: str, auto_category: str) -> str`

Rules:

- Document level: one LLM call over roughly the first 2000 characters. Low confidence or LLM failure → `uncategorized`. Keyword heuristic if OpenRouter is down. Ingest **never** fails because classification failed.
- Chunk level: keyword/scoring heuristic only. Above threshold → that category; else inherit `auto_category`. **No LLM per chunk.**
- Stamped ingest does not call this module (Task 12).

- [ ] **Step 1: Write failing tests** with the LLM stubbed: unmatched content → `uncategorized`; mixed budget+timeline document → chunk-level `financial` and `pm` both appear; LLM raise → heuristic, not exception.
- [ ] **Step 2: Implement classifier.**
- [ ] **Step 3: Run tests — expect PASS.**
- [ ] **Step 4: Commit** `feat: classify documents by LLM and chunks by heuristic`

---



### Task 11: LanceDB vectorstore (build-then-swap)

**Files:**

- Create: `outskillai/packages/rag_engine/vectorstore.py`
- Test: `outskillai/tests/test_vectorstore.py`

**Interfaces:**

- Consumes: Task 4 prefilter proof, Task 6 embedder, Task 5 types
- Produces:
  - `connect_kb() -> LanceDB`
  - `build_table(chunks: list[Chunk], embedder) -> TableHandle` writing a **new** table named `kb_<uuid>`
  - `search(handle, query, where_sql: str | None, k: int) -> list[Chunk]`
  - `sql_where(column: str, values: list[str]) -> str` — the **only** place SQL values are quoted
  - `distance_to_relevance(distance: float) -> float` — cosine similarity `[0, 1]`, higher-is-better

Rules:

- Filters are SQL predicate strings: `.where("category = 'pm'")`. Never interpolate raw filenames.
- Never store NULL category.
- Always pass `prefilter=True`.
- Convert `_distance` to `metadata.relevance` here; never surface raw distance.
- Do not mutate a live table. Old tables drop when no job references them (registry owns that; leaking one table for a hackathon is acceptable).

- [ ] **Step 1: Write failing tests:** relevance in `[0, 1]` and sorts descending; quoting helper does not break on a filename with a quote; search with `where category = 'pm'` returns only those rows.
- [ ] **Step 2: Implement** `vectorstore.py`**.**
- [ ] **Step 3: Run tests — expect PASS.**
- [ ] **Step 4: Commit** `feat: store chunks in LanceDB with SQL filters and cosine relevance`

---



### Task 12: Public retriever (ingest / retrieve / clear / list / set_category)

**Files:**

- Create: `outskillai/packages/rag_engine/retriever.py`
- Modify: `outskillai/packages/rag_engine/__init__.py` to re-export the five functions
- Test: `outskillai/tests/test_rag_engine.py`, `outskillai/tests/test_retriever.py`, `outskillai/tests/test_lifecycle.py`

**Interfaces:**

- Consumes: ingestion, classifier, vectorstore, embedder, types
- Produces: the five public functions. Active table pointer lives in a module-level registry object that FastAPI will hold in Task 21 — for now a `KbState` dataclass: `handle`, `documents`, `last_folder`, `failed_files`, `failed_urls`, `chunk_count`.

`ingest(folder_path, stamp=None)`**:**

1. Scan + caps (Task 8).
2. Load + chunk (Task 9).
3. If `stamp` is `"uncategorized"` → reject (`IngestRejected`); no swap.
4. If `stamp` in `{financial, pm, capex, policy}`: skip classifier; every chunk of every file and every `urls.txt` entry gets `category = stamp`, `auto_category = 'uncategorized'`, `overridden = true`.
5. If `stamp is None`: classify per Task 10; `urls.txt` stays `uncategorized` / `type = web`.
6. Dedupe within each document.
7. Embed (caller of HTTP will `to_thread` this).
8. `build_table` into a **new** table; swap `KbState.handle` only on success.
9. Return `IngestResult`. Partial file/URL failures still succeed if the new table swapped; those rows are only in `failed_*`.

`retrieve(..., category=...)`**:**

```
primary = search(query, where="category = 'pm'", k=top_k, prefilter=True)
if len(primary) >= MIN_PRIMARY:
    return RetrieveResult(chunks=primary, primary_count=len(primary))
fill = search(query, where=<exclude chunk_ids already in primary>, k=top_k - len(primary))
return RetrieveResult(
    chunks=primary + [c.with(cross_category=True) for c in fill],
    primary_count=len(primary),
)
```

Primary is category-matched only. **No** `OR type = 'web'`**.** Backfill fires only below `MIN_PRIMARY`. An agent with 3 or 4 primary chunks gets fewer than `TOP_K`. General's primary filter is `category IN ('uncategorized','policy')`. `primary_count` is in-category hits only.

`set_category(kb_id, document_id, category=None)`**:** writes `category` for **every chunk of that document**, leaves `auto_category` untouched, `overridden = true`. `category=None` writes literal `'uncategorized'`. No classifier runs. Unknown `document_id` → `False`.

`clear`**:** drops the active handle and empties `KbState`. No HTTP route in this slice.

- [ ] **Step 1: Write the §11 ingest + retrieval + lifecycle tests** in the three test files. Required cases (each is a named test, not a comment):

Ingest:

- Mixed folder (PDF, CSV, TXT, `urls.txt`) → categories, metadata, `failed_files` / `failed_urls` for bad inputs.
- CSV chunks never split a row; header repeated; `row_start` / `row_end` contiguous.
- PDF chunks never span a page; `metadata.page` accurate.
- Repeated boilerplate inside **one** document → one chunk.
- Identical content in **two files** → two chunks, both citable, both `chunk_count`s full.
- Unmatched document → `auto_category = 'uncategorized'`.
- Mixed document (budget + timeline) → chunk-level `financial` **and** `pm`.
- `stamp="financial"` stamps every file and every `urls.txt` entry `category='financial'`, `overridden=true`, `auto_category='uncategorized'`, **zero classifier calls**.
- `stamp=None` auto-classifies files; `urls.txt` stays `uncategorized`.
- `stamp="uncategorized"` raises `IngestRejected` and does not swap.
- Subdirectory-only folder → `IngestRejected`; nested files never parsed.
- Over `MAX_FILES` → `IngestRejected` without parsing. Over `MAX_FILE_MB` → `failed_files`, rest ingest.
- `urls.txt` > `MAX_URLS`, over `MAX_URL_BYTES`, non-text Content-Type → `failed_urls` with distinct reasons.
- latin-1 CSV ingests.

Retrieval:

- ≥`MIN_PRIMARY` `pm` chunks → only `pm`, all `cross_category=false`.
- 0 `pm` chunks → still returns chunks, **every one** `cross_category=true`, `primary_count==0`.
- `primary_count` is in-category only.
- **0** `pm` **+ auto-detect** `urls.txt` **→** `primary_count==0`, web chunks `cross_category=true` (v4.0 regression).
- Same corpus stamped `pm` → those web chunks count toward `primary_count`, `cross_category=false`.
- Exactly `MIN_PRIMARY` in-category chunks → exactly those, no backfill, even if `< TOP_K`.
- Category filter matching 3 of 20 rows returns all 3 with `k=5`.

Lifecycle:

- Reloading the same folder twice does not double chunk count.
- A reload that fails partway leaves the previous KB intact and queryable.
- A retrieve started against handle A still returns handle A's chunks after a successful swap to handle B (jobs capture the table handle at start). `retrieve` must accept the captured handle, not always read the global pointer. Task 20 passes that handle into the graph.
- `set_category` to `policy` or unmarked applies to every chunk, leaves `auto_category` unchanged.
- Reload after override resets to auto-classify (classifier runs again because stamp is omitted).
- New `KbState()` (simulating process restart) → `list_documents` is `[]` until ingest.

- [ ] **Step 2: Run the new tests — expect FAIL.**
- [ ] **Step 3: Implement** `retriever.py`**.** Keep a throwaway `scripts/smoke_ingest.py` that ingests one TXT and prints retrieved chunks for later agent work.
- [ ] **Step 4: Run** `pytest tests/test_rag_engine.py tests/test_retriever.py tests/test_lifecycle.py tests/test_chunker.py tests/test_lancedb_prefilter.py -v` **— expect PASS.**
- [ ] **Step 5: Commit** `feat: expose ingest, retrieve, and set_category with prefer-then-backfill`

---



### Task 13: Agent state and parent router

**Files:**

- Create: `outskillai/packages/agent_builder/state.py`
- Create: `outskillai/packages/agent_builder/parent_agent.py`
- Test: `outskillai/tests/test_parent_agent.py`

**Interfaces:**

- Consumes: built-agent set (start with `{"pm", "financial"}`)
- Produces: `AgentState` TypedDict with `Annotated[list, operator.add]` on fields specialists write (`findings`, `timeline_events`, `warnings`). `route(query: str, built: set[str]) -> list[str]` using structured output over an enum, then **intersect with** `built`.

Routing fallback:

- First slice (only PM + Financial built): if routing fails or names nobody in `built`, activate **both**.
- After General exists (Task 17): if routing fails, activate **General only**.

A router that returns `capex` before CapEx is built must fall through to the fallback, not crash.

- [ ] **Step 1: Write failing tests:** PM-only question → `["pm"]`; finance+timeline → both, order stable (`financial` then `pm` or the activation order you document and reuse in the formatter); `capex` from the model while CapEx is not built → both PM and Financial, no exception.

- [ ] **Step 2: Implement router with structured output + validation.**

- [ ] **Step 3: Run tests — expect PASS.** Stub the LLM.

- [ ] **Step 4: Commit** `feat: route queries onto the set of agents that actually exist`

---



### Task 14: PM and Financial specialists

**Files:**

- Create: `outskillai/packages/agent_builder/financial_agent.py`
- Create: `outskillai/packages/agent_builder/pm_agent.py`
- Test: `outskillai/tests/test_specialists.py`

**Interfaces:**

- Consumes: `retrieve()`, `primary_count`, Tavily/NewsAPI wrappers, `shared.llm`
- Produces: each agent function `run_pm(state) -> dict` / `run_financial(state) -> dict` returning `summary`, `key_points`, `evidence[]`, `used_chunk_ids[]`, plus a timeline event.

Each agent:

1. Rewrite a sub-question.
2. `retrieve(kb_id, sub_question, category=...)`.
3. Live web **only if** `primary_count == 0` (these two agents). Never use `len(chunks)`.
4. Synthesize on OpenRouter. Prompt must label `cross_category` chunks as "related material from outside this domain" and live-web as web sources.
5. Return findings plus `used_chunk_ids` of chunks it actually used.
6. On `AGENT_TIMEOUT` or exception: timeline `failed` with `error`; do not raise into the graph.

Keep graph nodes **sync**. FastAPI runs `await asyncio.to_thread(graph.invoke, ...)`. Every embed and LanceDB search inside retrieve is therefore already off the event loop. Do not mix async nodes with sync LanceDB calls. If Tavily, NewsAPI, or OpenRouter raise, catch, append a job warning, and continue with retrieved chunks (possibly none).

- [ ] **Step 1: Write failing tests** with a fake retriever: `primary_count==0` triggers a web-search stub; `primary_count>=1` does not; returned `used_chunk_ids` are a subset of retrieved ids.

- [ ] **Step 2: Implement both agents sharing an internal** `run_specialist(name, category, live_web_if_empty)` **helper in a new** `packages/agent_builder/specialist.py` **so CapEx/General do not copy-paste later. Do not leave Financial/PM as the only copies.**

- [ ] **Step 3: Run tests — expect PASS.**

- [ ] **Step 4: Commit** `feat: add PM and Financial specialists keyed on primary_count`

---



### Task 15: LangGraph sequential, then Send

**Files:**

- Create: `outskillai/packages/agent_builder/graph.py`
- Test: `outskillai/tests/test_graph.py`

**Interfaces:**

- Consumes: parent router, specialists, `AgentState` with `operator.add` reducers
- Produces: `build_graph(built_agents: set[str]) -> CompiledGraph`; `run_job(query, kb_handle, job_updater)` that writes timeline statuses `queued → routing → running → merging → formatting → completed` (formatting is Task 16; this task can stop at merge and leave a `merged_findings` blob).

`Send` parallelism is an optimization. Sequential agents must produce the identical merged findings. If `Send` debugging burns time, **ship sequential** and continue to Task 17.

- [ ] **Step 1: Sequential graph test:** two agents both write findings; reducer concatenates; one agent raising still returns the other (`failed` on timeline).

- [ ] **Step 2: Implement sequential graph.**

- [ ] **Step 3: Add** `Send` **fan-out.** Same tests must pass. One failed agent does not hide the others.

- [ ] **Step 4: Timeout test:** an agent exceeding `AGENT_TIMEOUT` is `failed` and does not stall the job. Four sequential agents at `AGENT_TIMEOUT` complete inside `JOB_TIMEOUT` (assert `4 * AGENT_TIMEOUT < JOB_TIMEOUT` and a fake clock or a unit test that the job wrapper enforces `JOB_TIMEOUT`).

- [ ] **Step 5: Commit** `feat: fan-in specialist findings through LangGraph reducers`

---



### Task 16: Formatter and citations

**Files:**

- Create: `outskillai/packages/agent_builder/formatter.py`
- Test: `outskillai/tests/test_formatter.py`
- Create: `frontend/src/fixtures/` copies of real output (directory may be empty until UI plan; write JSON files here)

**Interfaces:**

- Consumes: merged agent findings, the chunk objects each agent was handed, `warnings[]`
- Produces: the completed §7.3 envelope. `format_job(...) -> dict`

Citation algorithm (deterministic; agents never mint ids):

1. For each agent, intersect `used_chunk_ids` with the chunk ids **actually handed to that agent**; drop the rest (no citation minted from a foreign or invented id).
2. Assign `c1..cn` over the **deduplicated union**, stable order: first appearance across agents in **activation order**.
3. One chunk → exactly one citation id even if two agents used it; both sections reference that id.
4. Drop any `citation_id` in a section that does not map to a real chunk; append a warning. Job still completes.
5. `quote`:
  - `pdf` / `txt` / `web`: first ~200 characters of chunk content.
  - `csv`: the repeated header line **plus the first data rows** that fit in ~200 characters — never the header alone.
6. Every `quote` is a literal substring of that chunk's `content`.
7. Copy top-level `warnings[]` into `result.warnings[]` so they stay identical.
8. Template loader: if files exist under `resource/` / `out/`, apply them; if missing, use this default shape. Missing templates must not fail the job.

- [ ] **Step 1: Write failing tests**

Put these helpers at the top of `tests/test_formatter.py`, then the four tests below.

```python
from packages.rag_engine.types import Chunk, ChunkMetadata
from packages.agent_builder.formatter import format_job

def _chunk(chunk_id: str, content: str, type_: str = "txt") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        metadata=ChunkMetadata(
            document_id="doc_1",
            source="charter.pdf" if type_ != "csv" else "budget.csv",
            type=type_,
            category="pm",
            auto_category="pm",
            page=1 if type_ == "pdf" else None,
            row_start=1 if type_ == "csv" else None,
            row_end=2 if type_ == "csv" else None,
            relevance=0.9,
            cross_category=False,
        ),
    )

def _finding(agent: str, used_chunk_ids: list[str]):
    return {
        "agent": agent,
        "title": agent,
        "summary": "summary",
        "body": "body",
        "key_points": ["point"],
        "used_chunk_ids": used_chunk_ids,
        "citation_ids": [],
    }
```

```python
def test_invented_used_chunk_id_is_dropped():
    handed = [_chunk("chk_real", "alpha text about budget")]
    envelope = format_job(
        query="q",
        activated=["pm"],
        findings=[_finding("pm", used_chunk_ids=["chk_real", "chk_invented"])],
        handed={"pm": handed},
        warnings=[],
    )
    assert [c["id"] for c in envelope["citations"]] == ["c1"]
    assert "c2" not in {c["id"] for c in envelope["citations"]}
    assert envelope["warnings"]  # invented id dropped, warning appended

def test_two_agents_same_chunk_share_one_citation_id():
    shared = _chunk("chk_budget", "region,quarter,revenue\neast,Q1,10")
    envelope = format_job(
        query="q",
        activated=["financial", "pm"],
        findings=[
            _finding("financial", used_chunk_ids=["chk_budget"]),
            _finding("pm", used_chunk_ids=["chk_budget"]),
        ],
        handed={"financial": [shared], "pm": [shared]},
        warnings=[],
    )
    assert len(envelope["citations"]) == 1
    assert envelope["citations"][0]["id"] == "c1"
    assert envelope["answer"]["sections"][0]["citation_ids"] == ["c1"]
    assert envelope["answer"]["sections"][1]["citation_ids"] == ["c1"]

def test_csv_quote_includes_header_and_data_row():
    csv_chunk = _chunk(
        "chk_csv",
        "region,quarter,revenue,budget\neast,Q1,10,12\nwest,Q1,20,18",
        type_="csv",
    )
    envelope = format_job(
        query="q",
        activated=["financial"],
        findings=[_finding("financial", used_chunk_ids=["chk_csv"])],
        handed={"financial": [csv_chunk]},
        warnings=[],
    )
    quote = envelope["citations"][0]["quote"]
    assert "region,quarter,revenue,budget" in quote
    assert "east,Q1,10,12" in quote
    assert quote in csv_chunk.content

def test_quote_is_substring_of_chunk_content():
    chunk = _chunk("chk_txt", "The milestone slips to November if hiring freezes.")
    envelope = format_job(
        query="q",
        activated=["pm"],
        findings=[_finding("pm", used_chunk_ids=["chk_txt"])],
        handed={"pm": [chunk]},
        warnings=[],
    )
    assert envelope["citations"][0]["quote"] in chunk.content
```

- [ ] **Step 2: Implement** `formatter.py`**.**

- [ ] **Step 3: Save real outputs** as `frontend/src/fixtures/job-completed-multi.json`, `job-cross.json`, `job-agent-failed.json`, `job-dropped-citation.json`, `job-failed.json` once a formatter run exists. If agents are stubbed, still emit valid §7.2 / §7.3 envelopes.

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit** `feat: derive citations in the formatter and emit the default JSON envelope`

---



### Task 17: CapEx and General

**Files:**

- Create: `outskillai/packages/agent_builder/capex_agent.py`
- Create: `outskillai/packages/agent_builder/general_agent.py`
- Modify: `outskillai/packages/agent_builder/parent_agent.py` (`built` may now include `capex` and `general`; routing-fail fallback becomes General only)
- Modify: `outskillai/packages/agent_builder/specialist.py` live-web rule parameter
- Test: `outskillai/tests/test_specialists.py` (extend), `outskillai/tests/test_parent_agent.py` (fallback)

**Interfaces:**

- Consumes: the same `run_specialist` helper
- Produces: CapEx (`category='capex'`, live web iff `primary_count==0`); General (`category=['uncategorized','policy']`, live web iff `primary_count < GENERAL_THIN_PRIMARY` or parent `needs_current_info is True`)

- [ ] **Step 1: Tests for General's filter and live-web rule; routing-fail →** `["general"]` **only.**
- [ ] **Step 2: Implement both agents. Wire them into** `build_graph`**.**
- [ ] **Step 3: Commit** `feat: add CapEx and General specialists with distinct live-web rules`

---



### Task 18: Minimal Pactlify PDF

**Files:**

- Create: `outskillai/packages/agent_builder/pdf_generator.py`
- Test: `outskillai/tests/test_pdf_generator.py`

**Interfaces:**

- Consumes: §7.3 envelope
- Produces: `render_pdf(envelope: dict) -> bytes`. Prefer WeasyPrint; if system deps are missing at import, use ReportLab. Contents: title **Pactlify**, date, job id, query, summary, agent sections, citations, source table.

Rendering is **eager** inside the formatting step (Task 21 wires this). If render raises: catch, `pdf_available = false`, append a warning, still complete the job. Keep the renderer simple — it sits inside `JOB_TIMEOUT`.

- [ ] **Step 1: Test that bytes start with** `%PDF` **for a minimal envelope; a renderer exception is not raised to the caller of a** `safe_render` **wrapper.**

- [ ] **Step 2: Implement generator +** `safe_render`**.**

- [ ] **Step 3: Commit** `feat: render a minimal Pactlify PDF from the job envelope`

---



### Task 19: Auth, ingest-root guard, and job registry

**Files:**

- Create: `outskillai/apps/api/auth.py`
- Create: `outskillai/apps/api/paths.py`
- Create: `outskillai/apps/api/session_registry.py`
- Test: `outskillai/tests/test_auth_paths.py`, `outskillai/tests/test_registry.py`

**Interfaces:**

- Consumes: `ADMIN_TOKEN`, `ALLOWED_INGEST_ROOT`, `JOB_RETENTION_*`
- Produces:
  - `require_admin(authorization: str) -> None` raising 401 `{error: unauthorized}`
  - `resolve_ingest_path(folder_path: str) -> Path` raising 400 `bad_folder` or 403 `forbidden_path`
  - `JobRegistry` with active KB pointer, document list, jobs; `evict()` keeps ≤50 jobs, LRU by last access, drops completed jobs older than 30 minutes, **never evicts a running job**

Path enforcement (copy exactly):

```python
root = Path(ALLOWED_INGEST_ROOT).resolve(strict=True)
target = Path(folder_path).resolve(strict=True)
if os.path.commonpath([root, target]) != str(root):
    raise Forbidden("forbidden_path")
```

Resolve before the check, ingest the **resolved** path. `strict=True` so a nonexistent path errors here.

- [ ] **Step 1: Write failing tests**
  - `/allowed-evil` against root `/allowed` → 403
  - symlink inside the root pointing outside → 403
  - missing/wrong bearer → 401
  - oldest completed job past retention → `job_not_found`; running job still present

- [ ] **Step 2: Implement the three modules.**

- [ ] **Step 3: Run tests — expect PASS.**

- [ ] **Step 4: Commit** `feat: guard admin ingest paths and bound the in-memory job registry`

---



### Task 20: FastAPI routes and CORS

**Files:**

- Create: `outskillai/apps/api/main.py`
- Create: `outskillai/apps/api/routes.py`
- Test: `outskillai/tests/test_api.py`

**Interfaces:**

- Consumes: retriever, graph, formatter, pdf `safe_render`, auth, paths, registry
- Produces: every endpoint in the wire-contract table. `GET /kb.loaded` must match `GET /admin/status.loaded`. After process start with no ingest: `loaded: false`, `document_count: 0`.

Implementation notes:

- CORS allows the React origin and the `Authorization` header.
- `POST /admin/ingest` is sync work; run `ingest(...)` in `asyncio.to_thread`. On `IngestRejected` → 400 `bad_folder`, no swap. Body `category` omitted or `null` → `stamp=None`. Body `category: "uncategorized"` → 400 `bad_folder`.
- `PATCH /admin/documents/{id}`: `{ "category": "policy" }` or `{ "category": null }` (unmark). Other values → 400. Unknown id → 404. `200 { "ok": true, "document": DocumentInfo }`.
- `POST /query`: trim whitespace; empty → 400 `empty_query`; no swapped KB → 409 `kb_empty` with message `Knowledge base not loaded — ask admin.`; else create `job_id`, status `queued`, start graph in a background task, return `{ job_id }`.
- Background job: capture the **current table handle** at start; a later ingest swap must not change that job's retrieve target. Status progression uses the seven-state enum. On `JOB_TIMEOUT`, format whatever completed, add a warning, mark `completed` — never leave `running`. All agents fail → `failed`, `error` short reason, `result: null`, no fabricated answer. Eager PDF bytes stored on the job.
- `GET /status/{job_id}`: unknown → 404 `{error: job_not_found}`. Touch LRU access time.
- `GET /report/{job_id}/pdf`: 200 PDF bytes only if completed and `pdf_available`; else 404 `{error: pdf_not_ready}`.
- LangSmith env must never block an answer.
- No `clear()` route.

- [ ] **Step 1: Write failing API tests (httpx** `TestClient` **or** `AsyncClient`**)** covering the §11 Agents and API list:
  - Empty KB → `POST /query` 409 `kb_empty`
  - Empty question → 400 `empty_query`, no job
  - One agent failure → merged answer; that agent `failed` on timeline
  - Invented citation dropped; warning; job completes
  - `used_chunk_id` never handed → dropped
  - Two agents, one chunk → one citation
  - Quotes are substrings; CSV quote has header **and** a data row
  - `/admin/*` missing/wrong token → 401 `{error: unauthorized}`
  - Path outside root → 403 `{error: forbidden_path}`
  - Empty/missing folder ingest → 400 `{error: bad_folder}`, no swap
  - `GET /admin/documents` empty KB → `200 { "documents": [] }`
  - `GET /report/{id}/pdf` → `application/pdf` when available; else 404 `pdf_not_ready`
  - `GET /kb` has no path or filenames; after "restart" (new registry) `loaded: false`
  - `PATCH` `{ "category": null }` unmarks every chunk, `overridden=true`, `auto_category` unchanged
  - Unknown job → 404 `job_not_found`
  - Failed job: non-null top-level `error`, `result: null`
- [ ] **Step 2: Implement** `main.py` **+** `routes.py`**.**
- [ ] **Step 3: Run** `pytest tests/test_api.py tests/test_auth_paths.py tests/test_registry.py -v` **— expect PASS.**
- [ ] **Step 4: Commit** `feat: expose Pactlify admin and query HTTP contract`

---



### Task 21: Sample corpus and operator README

**Files:**

- Create: `outskillai/sample_data/` (flat — no subdirectories): 1–2 PDFs, 1 CSV, 1 TXT, `urls.txt`. **At least one deliberately mixed document** (budget + timeline in one file). Every file `< MAX_FILE_MB`; folder `< MAX_FILES`.
- Modify: `outskillai/README.md` with env vars, `ALLOWED_INGEST_ROOT` pointing at a parent of `sample_data`, `ADMIN_TOKEN`, and:

```
uvicorn apps.api.main:app --workers 1
```

**Interfaces:**

- Consumes: working ingest from Task 12
- Produces: a folder a judge can paste into Admin; smoke script still works

- [ ] **Step 1: Add sample files. Keep mixed-document content obviously** `financial` **and** `pm` **at chunk level.**
- [ ] **Step 2: Run smoke ingest against** `sample_data` **with the fake or real embedder.**
- [ ] **Step 3: Commit** `chore: add a flat sample_data folder and single-worker run docs`

---



### Task 22: Full backend pytest gate

**Files:** none new — run the suite

- [ ] **Step 1: Run**

```bash
cd outskillai
pytest -v
```

Expected: PASS. One integration test may use the real MiniLM model; everything else uses `FakeEmbedder`.

- [ ] **Step 2: Confirm OpenAPI** at `/openapi.json` matches the wire contract field names (`document_id`, `source`, `category`, seven-state `status`, `pdf_available`). The UI plan may generate `types.ts` from this schema.

- [ ] **Step 3: If formatter fixtures in** `frontend/src/fixtures/` **drifted from live envelopes, regenerate them from a real completed job.**

---



## Backend tests that must pass (checklist)

Copy of v4.0 §11 as it applies to this plan. Every bullet has a test function in Tasks 7–20.

**Ingest, retrieval, lifecycle:** listed in Task 12. **Agents and API:** listed in Task 20. **Pre-filter:** Task 4 + Task 12. **Formatter:** Task 16. **PDF:** Task 18. **Auth/path/retention:** Task 19.

---



## Backend gotchas (do not "fix" these into the old bugs)

- Primary filter must not include `OR type = 'web'`. Unstamped web is backfill, `cross_category=true`.
- Live web reads `primary_count`, not `len(chunks)`.
- Stamped batch writes `auto_category='uncategorized'`, not the stamp.
- `category=None` on ingest is auto-detect; on `set_category` it unmarks.
- `startswith` on ingest paths is wrong; use `resolve` + `commonpath`.
- `--workers 2` makes empty-KB bugs intermittent. Do not.
- Embed/search on the event loop freeze status polls. `to_thread`.
- Reload must not `add()` onto the live table.
- Parallel agents need `operator.add` reducers.
- CSV quotes need header **plus** data rows.
- Dedupe is per document, never across documents.
- `JOB_TIMEOUT` is 300s because sequential fallback is 4 × 60s.
- `relevance` is cosine similarity, higher-is-better.

---



## Deferred (backend)

- Custom JSON/PDF templates as the primary renderer (`resource` / `out` loader may exist; default envelope is required).
- HTTP `clear()`. Function exists; no route.
- Rate limit on `POST /query`.
- Recursive folder ingest.
- Re-classify on demand.
- Durable LanceDB, `memory://` if verified, saved overrides, `categories.txt`.
- Chunk-level LLM classification.

---



## Suggested execution

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.
2. **Inline Execution** — this session, `executing-plans`, checkpoints after Tasks 4, 12, 16, 20.

Frontend can proceed in parallel against fixtures; swap `api.ts` to live `fetch` only after Task 20.