# Multi-Agent AI Deep Researcher — Architecture & Build Plan (v2.0)

Consolidated from `Updated-Architecture-and-Build-Plan.md` plus the accepted findings in `Updated-Architecture-and-Build-Plan-opus.md`. **This file is the source of truth for implementation.** The other two are history.

**Product:** Admin loads a shared document folder into an in-memory knowledge base. Client users ask a question. A parent agent routes to specialist agents (Financial, PM, CapEx, General). Agents retrieve from category-preferring RAG, optionally search the live web, merge findings, and return a cited answer.

**First slice focus:** PM and Financial agents, folder ingest, Admin | Client toggle UI, default JSON response. CapEx, General, custom templates, PDF, login, and disk persistence follow in later iterations.

**What changed from the previous version.** Category filtering is now *preference with flagged backfill* instead of a hard filter (§4.4) — this was the one flaw that would have silently lost evidence. The classifier may now return `uncategorized`. Reload builds a new table and swaps atomically. `EphemeralClient()` was not a real LanceDB API and is replaced. Timeouts, an admin token, and a job-status contract are now specified. Phase order is unchanged from the previous plan.

---



## 1. Locked decisions


| Topic                      | Decision                                                                                                                                                                                                     |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Backend                    | Two modules only: `rag_engine` and `agent_builder`. FastAPI is thin glue, not a third product.                                                                                                               |
| UI                         | One React + TypeScript app. Header toggle **Admin | Client**. Login and roles replace the toggle later. Look-and-feel / widgets later.                                                                       |
| Vector DB                  | **LanceDB**, per-process temp directory, discarded on exit. After every restart, admin provides a folder path; the app rebuilds the vector DB.                                                               |
| Process model              | **Single worker.** `uvicorn --workers 1`, no `--reload`. The KB and job registry are in-process state.                                                                                                       |
| Who adds documents         | Office admin only. One shared knowledge base. Clients never upload.                                                                                                                                          |
| Folder shape               | One folder. Scan `pdf`, `csv`, `txt`, and `urls.txt`. Auto-classify each file.                                                                                                                               |
| Categories                 | Auto-classify assigns `financial`, `pm`, `capex`, or `uncategorized` (low confidence). Only admin can retag as `policy` or clear the tag (unmarked **quick doc**).                                           |
| Classification granularity | Per **document** (shown in the admin table) **and** per **chunk** (used for retrieval). See §4.2.                                                                                                            |
| Overrides                  | In memory only. Reload or restart auto-classifies again.                                                                                                                                                     |
| Client query               | Question text only. No source picker. Parent routes automatically.                                                                                                                                           |
| Agents                     | All four exist and use the same pattern. First build: **PM + Financial**. Then CapEx + General.                                                                                                              |
| Retrieval filtering        | **Preference, not exclusion.** An agent's category is preferred; if it yields fewer than `MIN_PRIMARY` chunks, the shortfall is backfilled from the rest of the KB and flagged `cross_category`.             |
| Live web                   | Triggered on the **primary** (in-category) result only, never on the backfilled total. General: if primary is thin **or** the question needs current info. Financial / PM / CapEx: only if primary is empty. |
| Ingested web               | `urls.txt` in the admin folder is ingested as type `web`, category `uncategorized`. URLs are not auto-classified as financial / pm / capex.                                                                  |
| Response / PDF             | Custom JSON and PDF templates later, stored under app `resource` / `out`. Until then, use the default JSON shape in §7. PDF control hidden/disabled.                                                         |
| Citations                  | Derived by the formatter from chunks actually retrieved. Agents never mint citation ids. `quote` is copied from chunk text, never model-written.                                                             |
| Admin endpoints            | Guarded by `ADMIN_TOKEN`. Ingest paths must resolve under `ALLOWED_INGEST_ROOT`.                                                                                                                             |
| External services          | Keep OpenRouter, Tavily, NewsAPI, LangSmith. Chat model is `OPENROUTER_MODEL` in `.env` (default: `openai/gpt-4o-mini`). If one service fails, continue with what works.                                     |
| Persistence                | No durable LanceDB and no saved overrides in this slice.                                                                                                                                                     |


---



## 2. Architecture



### 2.1 Original architecture diagram

Copied from `Updated Architecture & Build Plan_v1.0.docx`, kept for provenance.

> **Historical — do not implement from this diagram.** Three boxes no longer exist in the design: **Upload Files**, **Source Selection**, and `POST /upload`. Admin folder ingest replaced all three. The `PM Agent / Policy` label is also stale; PM is Project Manager, and `policy` is a document category, not an agent.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        USER                                          │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│              FRONTEND (React + TypeScript)                           │
│                                                                      │
│   ┌──────────┐   ┌───────────┐   ┌────────────┐   ┌──────────────┐   │
│   │ Upload   │   │ Query     │   │ Agent      │   │ Response     │   │
│   │ Files    │   │ Input     │   │ Timeline   │   │ Viewer +     │   │
│   │ PDF/CSV/ │   │ + Source  │   │ (live)     │   │ PDF Download │   │
│   │ TXT/Web  │   │ Selection │   │            │   │              │   │
│   └────┬─────┘   └─────┬──-──┘   └─────┬──────┘   └──────┬───────┘   │
│        └───────────────┴───────────────┴─────────────────┘           │
│                              │ HTTP                                  │
└──────────────────────────────┼─────────────────────────────────────-─┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│              API LAYER (FastAPI)                                     │
│                                                                      │
│   POST /upload   POST /query   GET /status/{id}  GET /report/{id}/pdf│
│                                                                      │
│   ┌──────────────────────────────────────────────────────────────┐   │
│   │           Session / Job Registry                             │   │
│   │   (tracks uploaded files, query jobs, results)               │   │
│   └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
                 ▼                           ▼
┌──────────────────────────────┐  ┌─────────────────────────────────────┐
│   PACKAGE 1: RAG ENGINE      │  │   PACKAGE 2: AGENT BUILDER          │
│                              │  │                                     │
│   ┌────────────────────┐     │  │   ┌────────────────────────────┐    │
│   │  Ingestion Layer   │     │  │   │  PARENT BUILDER AGENT      │    │
│   │  - PDF (PyMuPDF)   │     │  │   │  (orchestrator + router)   │    │
│   │  - CSV (pandas)    │     │  │   └──────────┬───────────────-─┘    │
│   │  - TXT (direct)    │     │  │              │                      │
│   │  - Web (loader)    │     │  │   ┌──────────┴───────────────-─┐    │
│   └────────┬───────────┘     │  │   │  Decides which agents      │    │
│            ▼                 │  │   │  to invoke based on query  │    │
│   ┌────────────────────┐     │  │   └──────────┬────────────-────┘    │
│   │  Chunking + Clean  │     │  │              │                      │
│   │  - Split by size   │     │  │   ┌──────────┼──────────────┐       │
│   │  - Overlap window  │     │  │   │          │              │       │
│   └────────┬───────────┘     │  │   ▼          ▼              ▼       │
│            ▼                 │  │ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ │
│   ┌────────────────────┐     │  │ │FINAN-│ │ PM   │ │CAPEX │ │GENER-│ │
│   │  Embedding Model   │     │  │ │CIAL  │ │AGENT │ │AGENT │ │AL    │ │
│   │  (free, local)     │     │  │ │AGENT │ │Policy│ │      │ │AGENT │ │
│   │  sentence-         │     │  │ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ │
│   │  transformers      │     │  │    │        │        │        │     │
│   └────────┬───────────┘     │  │    ┌───----─┴────────┴──────-─┘     │
│            ▼                 │  │    │     All run in PARALLEL  |     │
│   ┌────────────────────-┐    │  │    │     (LangGraph Send API) |     │
│   │  IN-MEMORY VECTOR   │    │  │    └──────---─────┬──────────-┘     |
│   │  DATABASE           │    │  │                   │                 │
│   │  (LanceDB           │    │  │         ┌─────────▼───────---───┐   │
│   │   ephemeral mode)   │    │  │         │  FAN-IN MERGE         │   │
│   │                     │    │  │         │  (combines all agent  │   │
│   │  Stores:            │    │  │         │   outputs into one    │   │
│   │  - Document chunks  │    │  │         │   result)             │   │
│   │  - Metadata         │    │  │         └─────────┬─────────---─┘   │
│   │  - Embeddings       │    │  │                   │                 │
│   │  - Source info      │    │  │         ┌─────────▼───────----───┐  │
│   └────────┬───────────-┘    │  │         │  RESPONSE FORMATTER    │  │
│            │                 │  │         │  (applies your specific│  │
│   ┌────────▼───────────┐     │  │         │outputformat with praph)│  │
│   │  RETRIEVAL         │     │  │         └─────────┬─────────----─┘  │
│   │  INTERFACE         │     │  │                   │                 │
│   │  query → chunks +  │     │  │         ┌─────────▼───────--───┐    │
│   │  metadata          │     │  │         │  PDF REPORT          │    │
│   └────────────────────┘     │  │         │  GENERATOR           │    │
│                              │  │         │  (only if user asks) │    │
│                              │  │         └──────────────────────┘    │
│                              │  │                                     │
│  OpenRouter LLM ◄────────────┼──┼───────────────────────────────────-─┘
│  LangSmith Tracing ◄─────────┼──┼─────────────────────────────────────┘
└──────────────────────────────┘  └────────────────────────────-------──┘
                               │
                               │  RAG Engine exposes:
                               │  - ingest(files) → knowledge_base_id
                               │  - retrieve(kb_id, query) → chunks
                               │  - clear(kb_id)
                               │
                               │  Agent Builder calls:
                               │  - retrieve() from RAG Engine
                               │  - OpenRouter for LLM calls
                               │  - Tavily/NewsAPI for external search
                               │  - LangSmith for tracing
                               │
                               ▼
                     ┌────────────────-─┐
                     │  SHARED RESOURCES│
                     │                  │
                     │  OpenRouter API  │
                     │  Tavily API      │
                     │  NewsAPI         │
                     │  LangSmith       │
                     │  Embedding Model │
                     └────────────────-─┘
```



### 2.2 Refined architecture (implement this)

```
[ One React app ]
  toggle: Admin | Client
        |
        | HTTP  (admin routes carry ADMIN_TOKEN)
        v
[ Thin FastAPI glue ]  -- single worker
  routes, CORS, in-memory job registry, env keys
        |
   +----+----+
   v         v
[ rag_engine ]     [ agent_builder ]
 folder ingest     parent router
 auto-classify     financial / pm / capex / general
 doc + chunk tags  retrieve() + optional live web
 LanceDB (tmpdir)  merge -> formatter -> optional PDF later
 retrieve/clear    citations derived here
```

**rag_engine** owns files, chunking, local embeddings, LanceDB, and `ingest` / `retrieve` / `clear` / `list_documents` / `set_category`. It does not call the chat LLM for answers. It may call a small classifier model or heuristic to assign categories.

**agent_builder** owns the parent, four specialist agents, LangGraph fan-out, merge, formatter, and PDF later. It never parses files. It only calls `retrieve()` and external APIs.

**Shared in-process imports.** Both packages run inside the FastAPI process. No HTTP between packages.

### 2.3 LanceDB connection

There is no `lancedb.EphemeralClient()` — that was a ChromaDB-shaped API inherited from the v1.0 docx. Use a per-process temp directory:

```python
import tempfile, lancedb

_KB_DIR = tempfile.mkdtemp(prefix="outskill-kb-")
db = lancedb.connect(_KB_DIR)
```

Behaviour matches the intent: the directory is per-process and discarded, a restart yields an empty KB, and the admin must supply the folder path again. If you want true RAM residency later, verify a `memory://` connection string against the installed version during **Phase 1**, not while debugging Phase 2.

Two consequences that shape `vectorstore.py`:

- **Filters are SQL predicate strings**, not dicts: `.where("category IN ('pm','capex') OR type = 'web'")`. Build these through one helper that quotes values, since filenames and categories come from user-controlled folder contents.
- **Never store a NULL category.** SQL `category = 'x'` does not match NULL, and neither does `category != 'x'`. Unmarked documents store the literal string `'uncategorized'`.



### 2.4 Repository layout

```
outskillai/
├── frontend/                      # One React + TypeScript app
│   └── src/types.ts               # Mirrors §7 + §7.2 (or generated from OpenAPI)
├── apps/api/
│   ├── main.py
│   ├── routes.py
│   ├── auth.py                    # ADMIN_TOKEN check
│   └── session_registry.py        # Active KB pointer + jobs
├── packages/
│   ├── rag_engine/
│   │   ├── ingestion.py           # PDF / CSV / TXT / urls.txt
│   │   ├── chunker.py             # per-type chunking rules
│   │   ├── embeddings.py          # sentence-transformers/all-MiniLM-L6-v2
│   │   ├── classifier.py          # doc-level LLM + chunk-level heuristic
│   │   ├── vectorstore.py         # LanceDB connect / build / swap / filter SQL
│   │   └── retriever.py           # public ingest / retrieve / clear / documents
│   └── agent_builder/
│       ├── parent_agent.py
│       ├── financial_agent.py
│       ├── pm_agent.py
│       ├── capex_agent.py
│       ├── general_agent.py
│       ├── graph.py
│       ├── state.py
│       ├── formatter.py           # builds citations deterministically
│       └── pdf_generator.py       # later
├── shared/
│   ├── config.py                  # all limits from §4.6 live here
│   └── llm.py                     # OpenRouter wrapper + timeout/retry
├── tests/
│   ├── fake_embedder.py           # deterministic vectors for unit tests
│   ├── test_rag_engine.py
│   └── test_agents.py
├── resource/                      # later: JSON / PDF templates
├── out/                           # later: generated reports
└── sample_data/                   # test folder for admin ingest
```

---



## 3. UI — one app, two modes

Look-and-feel and widget styling are out of this slice. Behavior is in scope.

**Shared chrome:** app name, **Admin | Client** toggle, connection/job status. No per-user history.

### Admin mode

- Folder path field + **Load / Reload**.
- Prompts once for the admin token and holds it in memory for the session. The toggle is UI convenience, **not** a security boundary — the token is what actually guards the endpoints.
- Rebuilds the shared LanceDB from that folder (build-then-swap, §4.3).
- Document table: filename, type, chunk count, **auto category** (`financial` / `pm` / `capex` / `uncategorized`), **effective category** (auto, or the admin override), override control (`policy` / clear / any of the four).
- Status: last folder, file count, per-file ingest errors, per-URL failures.
- Visible note: overrides are lost on reload or restart.
- Admin does not run research questions in this slice.



### Client mode

- Question box only. No upload. No source picker.
- Submit starts a job. **Agent timeline** updates as agents run, driven by the §7.2 payload.
- **Response viewer** shows the formatted JSON answer, with cross-category evidence visually marked.
- PDF download hidden/disabled until a PDF template exists.
- If the shared KB is empty: "Knowledge base not loaded — ask admin." Do not start a job.
- A `404` from `GET /status/{job_id}` means the job was lost to a restart. Show "job no longer available — please ask again," not a generic error.

---



## 4. Data flow



### 4.1 Admin loads the knowledge base

1. Admin pastes a folder path and clicks Load / Reload. Request carries `ADMIN_TOKEN`.
2. API resolves the path and rejects anything outside `ALLOWED_INGEST_ROOT`.
3. `rag_engine` scans `pdf`, `csv`, `txt`, and `urls.txt`.
4. Each file or URL is chunked per §4.2 with source metadata.
5. Chunks are classified per §4.2 and embedded with `sentence-transformers/all-MiniLM-L6-v2`.
6. Rows are written to a **new** table; the active pointer swaps only on success (§4.3).
7. API returns the shared `knowledge_base_id` (`shared`) and the document list, including failures.

`urls.txt` **fetching** runs with a **10s per-URL timeout** and **at most 5 concurrent** fetches. Without the timeout, §9's "bad URL → skip and list as failed" is unreachable, because a hanging request never becomes an error.

**Duplicate suppression.** Hash chunk content at ingest and skip exact duplicates. Repeated headers and footers otherwise crowd out real evidence inside `TOP_K`.

### 4.2 Chunking and classification

Chunking rules differ by type. This matters because metadata has to stay truthful.


| Type         | Rule                                                                                                                                                            |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `txt`, `web` | ~1000 characters, 200 overlap.                                                                                                                                  |
| `pdf`        | ~1000 characters, 200 overlap, **never spanning a page boundary** — otherwise `metadata.page` is a lie.                                                         |
| `csv`        | Accumulate whole rows until the next row would exceed the budget. **Never split mid-row.** Repeat the CSV header in every chunk. Carry `row_start` / `row_end`. |


Repeating the CSV header does more for CSV answer quality than anything else in the ingest path; a chunk of bare comma-separated values is nearly meaningless to both the embedder and the LLM.

**Classification runs at two levels.**

- **Document level (**`auto_category`**).** One LLM call per file over roughly the first 2000 characters, returning `financial` / `pm` / `capex` / `uncategorized`. On low confidence, or if the classifier call fails, the result is `uncategorized`. A keyword heuristic is the fallback if OpenRouter is down. This value is what the admin table displays.
- **Chunk level (**`category`**).** A keyword/scoring heuristic per chunk. If a chunk scores above threshold for a category, it takes that category; otherwise it inherits the document's `auto_category`. **No LLM call per chunk** — that would be hundreds of calls per folder.

This is why a project charter works: the budget table inside a PM-titled document carries `category = 'financial'` at the chunk level and is reachable by the Financial agent, while the document still shows as PM to the admin.

**Two columns, deliberately.** `auto_category` is what the classifier decided; `category` is what retrieval filters on. An admin override writes `category` for **every chunk of that document** and leaves `auto_category` untouched, so the admin table can always show both what the machine thought and what a human decided. An explicit override is authoritative and intentionally flattens any chunk-level variation within that document.

`urls.txt` entries are `type = 'web'`, `auto_category = 'uncategorized'`, `category = 'uncategorized'`.

### 4.3 Reload is build-then-swap

Never mutate the live table. Ingest into a new table (`kb_<uuid>`); when it completes successfully, atomically swap the registry's active pointer. Each job captures the table handle when it starts and keeps using that handle to completion.

This is required, not a nicety, for two reasons:

- **§9 promises** the KB "stays unchanged if a previous load succeeded." A rebuild-in-place cannot deliver that — a reload that fails halfway leaves a half-built corpus.
- An admin reload during a live client query would otherwise pull the corpus out from under running agents, producing a half-grounded answer or a crash mid-graph.

Old tables are dropped once no job references them. Leaking one table for a hackathon is acceptable.

**Reload replaces; it does not append.** Say it in code review terms: the obvious implementation (`table.add(...)` onto the existing table) silently doubles every chunk on every reload, and duplicated chunks consume the whole `TOP_K` budget with identical text.

### 4.4 Retrieval: prefer, then backfill

**This section replaces the previous hard category filter.** Real project documents are mixed — a charter contains budget, timeline, risks, and capital items in one file. Under a hard filter, one misclassification makes a document invisible to the agent that needs it, `retrieve` returns zero chunks, and the client gets "no evidence found" about a document sitting right there in the corpus. The failure is silent: nothing errors.

```
retrieve(kb, query, category="pm", top_k=TOP_K):
    primary = search(query, where="category = 'pm' OR type = 'web'", k=top_k)

    if len(primary) >= MIN_PRIMARY:
        return primary

    fill = search(query, where=<exclude ids already in primary>, k=top_k - len(primary))
    return primary + [c.with(cross_category=True) for c in fill]
```

A misclassification now degrades to "slightly off-domain evidence, clearly labelled" instead of "no evidence." Every backfilled chunk carries `cross_category = true` so the formatter, the UI, and your tests can all tell the difference.

**Live-web triggers read** `primary`**, not the returned total.** This preserves the original intent — "my domain has no documents, so go to the web." If the trigger used the post-backfill count it would essentially never fire, because backfill almost always returns something.


| Agent     | Primary filter                                           | Live web (Tavily / NewsAPI)                                                             |
| --------- | -------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Financial | `category = 'financial' OR type = 'web'`                 | Only if **primary** is empty (0 chunks)                                                 |
| PM        | `category = 'pm' OR type = 'web'`                        | Only if **primary** is empty (0 chunks)                                                 |
| CapEx     | `category = 'capex' OR type = 'web'`                     | Only if **primary** is empty (0 chunks)                                                 |
| General   | `category IN ('uncategorized','policy') OR type = 'web'` | If **primary** is thin (fewer than 2) **or** the parent set `needs_current_info = true` |


Backfill applies to all four agents, including General.

Do not use an LLM to decide "usefulness" in this slice. The thresholds are counts, deliberately.

### 4.5 Client asks a question

1. Client submits text. API validates it is non-empty and the KB is loaded, creates a `job_id`, and starts `agent_builder`.
2. Parent agent picks one or more specialists, constrained to the set of **built** agents (§6).
3. Each activated agent:
  - Rewrites a sub-question for its domain.
  - Calls `retrieve(kb_id, sub_question, category=…)` and inspects the primary count.
  - Optionally calls Tavily/NewsAPI per §4.4.
  - Synthesizes findings on OpenRouter, with cross-category and live-web evidence labelled as such in the prompt.
  - Returns findings **plus the chunk ids it actually used**.
4. Agents run in parallel via LangGraph `Send`. Fan-in merge uses a reducer (`operator.add`) so parallel writes do not overwrite each other.
5. Formatter merges, then derives citations deterministically (§7.1) and applies the default JSON shape, or a template from `resource` / `out` when present.
6. Client polls `GET /status/{job_id}` every ~1s for timeline updates and the final answer.

**Blocking work must leave the event loop.** `sentence-transformers` encoding and LanceDB search are synchronous CPU work. Called directly inside an `async def` route they freeze the whole server for the duration — no status polls, no health checks, a frontend that looks hung, and on a folder of real PDFs that is tens of seconds. Wrap every embed and every search in `await asyncio.to_thread(...)`. Use that one convention everywhere rather than mixing it with sync `def` routes.

### 4.6 Limits and timeouts

All of these live in `shared/config.py`. Nothing in the pipeline is unbounded.


| Name                           | Value                   | Why                                                                                                                        |
| ------------------------------ | ----------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 1000 / 200 chars        | Per §4.2, type-dependent                                                                                                   |
| `CSV_ROWS_PER_CHUNK`           | 10–50 rows, row-bounded | Large spreadsheets do not explode chunk count                                                                              |
| `TOP_K`                        | 5                       | Up to 4 agents × 5 chunks ≈ 20k chars of context. Comfortable for `gpt-4o-mini`; do not raise casually                     |
| `MIN_PRIMARY`                  | 3                       | Backfill threshold in §4.4. A starting guess — retune once you can see real retrieval on your own documents                |
| `LLM_TIMEOUT`                  | 30s                     | One retry on connection error only, never on timeout                                                                       |
| `AGENT_TIMEOUT`                | 60s                     | On expiry the agent is `failed` on the timeline; §9's partial-merge path covers the rest                                   |
| `JOB_TIMEOUT`                  | 150s                    | Format whatever completed, add a warning. A job must never sit in `running` forever — the UI has no escape from that state |
| `URL_FETCH_TIMEOUT`            | 10s                     | Per URL at ingest                                                                                                          |
| `URL_FETCH_CONCURRENCY`        | 5                       | One slow URL must not stall the folder load                                                                                |


For scale: a four-agent question is up to **10 LLM calls** (1 routing + 4 × (rewrite + synthesis) + 1 formatting) plus up to 4 web searches. Not a cost problem on `gpt-4o-mini`. Very much a latency problem, which is what these bounds exist for.

### 4.7 Restart

The temp directory is gone. Admin must provide the folder path again. Classification overrides are gone. In-memory jobs are gone.

---



## 5. Package interface

Agent Builder never touches file parsing, embeddings, or LanceDB internals.

```
ingest(folder_path: str) -> IngestResult      # always the shared KB; id is "shared"

retrieve(
  knowledge_base_id: str,
  query: str,
  top_k: int = TOP_K,
  category: str | list[str] | None = None,    # preference, not exclusion (§4.4)
  source_type: str | list[str] | None = None,
) -> RetrieveResult

clear(knowledge_base_id: str) -> bool

list_documents(knowledge_base_id: str) -> list[DocumentInfo]

set_category(knowledge_base_id: str, document_id: str, category: str | None) -> bool
```

`RetrieveResult`:

- `chunks`: list[Chunk] — primary results first, then backfill
- `primary_count`: int — **drives the live-web decision**; agents must read this, not `len(chunks)`

`Chunk`:

- `chunk_id`: str — stable, assigned at ingest; the formatter's citation source of truth
- `content`: str
- `metadata.document_id`: str
- `metadata.source`: filename or URL
- `metadata.type`: `pdf` / `csv` / `txt` / `web`
- `metadata.category`: effective category — `financial` / `pm` / `capex` / `policy` / `uncategorized`
- `metadata.auto_category`: what the classifier decided, before any override
- `metadata.page`: int (PDF)
- `metadata.row_start`, `metadata.row_end`: int (CSV) — a range, because a batch of rows is one chunk
- `metadata.relevance`: float
- `metadata.cross_category`: bool — true if this chunk was backfilled outside the requested category

`IngestResult`: `knowledge_base_id`, `documents: list[DocumentInfo]`, `failed_files: list[{name, reason}]`, `failed_urls: list[{url, reason}]`, `chunk_count`.

`DocumentInfo`: `document_id`, `source`, `type`, `chunk_count`, `auto_category`, `category`, `overridden: bool`.

`category=None` on `set_category` means unmarked quick doc, stored as `'uncategorized'`.

---



## 6. Agents

All four agents follow the same pattern and are equally capable. They differ only in system prompt, preferred category, and live-web rule.


| Agent           | Focus                                                         | Example question                                   |
| --------------- | ------------------------------------------------------------- | -------------------------------------------------- |
| Financial       | Revenue, costs, ROI, financial health, budgets                | "What is the financial impact of this project?"    |
| Project Manager | Timelines, milestones, risks, resource allocation             | "What is the project timeline and key risks?"      |
| CapEx           | Capital expenditures, asset depreciation, investment planning | "What capital investments are needed?"             |
| General         | Unmarked docs, policy, web, leftover questions                | "Summarize the key findings from these documents." |


Each agent returns `summary`, `key_points`, `evidence[]`, and `used_chunk_ids[]`.

**Every synthesis prompt must state the provenance of its evidence.** Chunks flagged `cross_category` are labelled "related material from outside this domain," and live-web results are labelled as web sources. An agent that cannot tell the difference will present off-domain evidence with the same confidence as in-domain evidence.

**Parent routing** activates 1–4 agents. Constrain the router to a structured output over an enum, then **validate against the set of agents that actually exist**. A router that returns `capex` during the first slice, when CapEx is not built, must fall through to the §9 fallback rather than crash.

- First slice (only PM + Financial built): pick from those two. If routing fails or the question fits neither, activate **both** so the client still gets an answer.
- After General exists: if routing fails, activate **General** only.

---



## 7. Response and status contracts



### 7.1 Citations are derived, never generated

`sections` claims must point at real citation ids, and nothing enforces that if the model mints them. A demo showing `[c7]` where no c7 exists undermines the entire cited-research pitch.

1. Chunks carry stable `chunk_id`s from ingest.
2. Each agent returns `used_chunk_ids[]` alongside its findings.
3. The **formatter** — not the agent — assigns `c1..cn` over that real chunk set and builds `citations[]` from chunk metadata.
4. Any `citation_id` appearing in a section that does not map to a real chunk is **dropped**, and a warning is appended to `warnings[]`.

`quote` is filled from the **first ~200 characters of the actual chunk content**. Never let the model write it: a model will paraphrase, and a paraphrase presented as a quotation is the worst possible bug in a research tool.

### 7.2 Job status (polled during a run)

`GET /status/{job_id}`:

```json
{
  "job_id": "string",
  "status": "queued | routing | running | merging | formatting | completed | failed",
  "query": "string",
  "created_at": "iso8601",
  "activated_agents": ["pm", "financial"],
  "timeline": [
    {
      "agent": "pm",
      "status": "pending | retrieving | searching_web | synthesizing | done | failed",
      "started_at": "iso8601",
      "finished_at": "iso8601 | null",
      "chunks_retrieved": 4,
      "primary_count": 4,
      "used_live_web": false,
      "error": null
    }
  ],
  "warnings": [],
  "result": null
}
```

`result` is `null` until `status = "completed"`, then it holds the §7.3 envelope. An unknown `job_id` returns **404**, which the client reads as "lost to restart" (§3).

### 7.3 Default final response

Custom JSON will be supplied later and loaded from `resource` / `out`. Until then, every completed job returns:

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
  "pdf_available": false
}
```

Every claim in `sections` points at a citation id, enforced per §7.1. The formatter applies this shape once after merge. Agents do not invent the final envelope.

`cross_category: true` on a citation must be visible in the UI. It is the difference between "your PM documents say this" and "no PM document covered it, so here is related material."

**PDF generator (later):** WeasyPrint from the formatted output. Title, date, report id, agent contributions, citations, source table. Only when the user asks and a template exists. Fallback if WeasyPrint system deps are missing: ReportLab.

---



## 8. API layer


| Endpoint                      | Auth          | Purpose                                                                                                                                   |
| ----------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /admin/ingest`          | `ADMIN_TOKEN` | Body: `{ "folder_path": "..." }`. Path must resolve under `ALLOWED_INGEST_ROOT`. Ingest folder, return `IngestResult`.                    |
| `GET /admin/documents`        | `ADMIN_TOKEN` | List documents with `auto_category`, `category`, `overridden`.                                                                            |
| `PATCH /admin/documents/{id}` | `ADMIN_TOKEN` | Body: `{ "category": "policy" | "uncategorized" | "financial" | "pm" | "capex" }`. In-memory override across all chunks of that document. |
| `GET /admin/status`           | `ADMIN_TOKEN` | Whether a KB is loaded, last folder, file counts, errors.                                                                                 |
| `POST /query`                 | none          | Body: `{ "query": "..." }`. Uses the shared KB. Returns `job_id`.                                                                         |
| `GET /status/{job_id}`        | none          | §7.2 payload. `404` if unknown.                                                                                                           |
| `GET /report/{job_id}/pdf`    | none          | Later. Hidden until PDF template exists.                                                                                                  |


**Why the admin routes are guarded.** The Admin | Client toggle is client-side UI state, not a security boundary. Without a token, `POST /admin/ingest` lets anyone who can reach the API make the server read an **arbitrary filesystem path** — `../../` walks anywhere the process can read, and that content comes straight back out through `GET /admin/documents` and through answers. On a laptop this is theoretical; it stops being theoretical the moment this runs on a shared network or a box for judging. Two env vars close it, and neither conflicts with real login later.

Session / job registry is an in-memory dict: active KB table pointer, document list, overrides, running jobs, completed results.

**Run single-worker.** With `--workers 2`, admin ingests into worker A while the client's query lands on worker B and sees an empty knowledge base — *intermittently*, depending on which worker gets the request. That is a brutal thing to debug late. Put it in the run command: `uvicorn apps.api.main:app --workers 1`. No `--reload` during a demo, since a reload wipes the KB.

CORS is enabled for the React app.

LangSmith: `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` in `.env`. Tracing must never block an answer.

`.env` keys: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (default `openai/gpt-4o-mini`), `TAVILY_API_KEY`, `NEWSAPI_API_KEY`, `LANGSMITH_API_KEY` / `LANGCHAIN_API_KEY`, `EMBEDDING_MODEL`, `ADMIN_TOKEN`, `ALLOWED_INGEST_ROOT`.

---



## 9. Errors and empty states

**Knowledge base**

- Empty or missing folder → Admin sees a clear error. KB stays empty, or unchanged if a previous load succeeded (guaranteed by build-then-swap, §4.3).
- Path outside `ALLOWED_INGEST_ROOT` → `403`, no ingest attempted.
- Missing or wrong `ADMIN_TOKEN` → `401`.
- Unreadable file → skip it, list it in `failed_files`, continue the rest.
- Bad or slow URL in `urls.txt` → skip after `URL_FETCH_TIMEOUT`, list it in `failed_urls`.
- Classifier LLM unavailable → fall back to the keyword heuristic; if that is inconclusive, `uncategorized`. Ingest never fails because classification failed.
- After restart, KB is empty until Admin loads a folder. Client cannot start a job.

**Query / agents**

- Empty question → reject, no job.
- KB not loaded → reject with a clear message, no job.
- Parent routing fails, or names an agent that is not built → first slice: activate both PM and Financial. After General exists: General only.
- One specialist fails or exceeds `AGENT_TIMEOUT` → job continues; that agent is `failed` on the timeline; merge uses the others.
- All agents fail → job status `failed` with a short reason. **No fabricated answer.**
- Primary retrieval empty → backfill supplies cross-category evidence, and the agent may call live web per §4.4. If both are empty, the agent reports "no evidence found."
- `JOB_TIMEOUT` exceeded → format whatever completed, add a warning, mark `completed`. Never leave a job `running`.
- OpenRouter / Tavily / NewsAPI / LangSmith down → continue with what works; add a warning on the job.

**Response / PDF**

- No custom template → default JSON. Do not fail the job.
- Invented citation id → dropped, warning added (§7.1). Do not fail the job.
- PDF not ready → client control hidden/disabled.

**Jobs**

- Server restart drops jobs. `GET /status/{job_id}` returns `404` and the client offers to ask again.

---



## 10. Build plan

Phase order is unchanged from the previous plan: the RAG engine is completed and tested before agent work begins.

**Accepted risk.** With horizontal phases there is no end-to-end path until Phase 5–6, so integration bugs all surface late and there is no fallback demo before then. Two hedges that do not change the structure:

- Record the fallback demo video (Phase 7) the **first** time the end-to-end path works, not at the end.
- During Phase 2, keep a throwaway script that ingests one TXT file and prints retrieved chunks. It costs nothing and gives Phase 3 a known-good corpus to develop against instead of a moving target.



### Phase 1 — Setup

Monorepo layout, Python venv, `shared/config.py` with every §4.6 limit, OpenRouter wrapper with timeout and retry, `.env` including `ADMIN_TOKEN` and `ALLOWED_INGEST_ROOT`, frontend shell with the Admin | Client toggle.

Pre-download the embedding model so the first run is not a surprise:

`python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"`

Confirm in a Python REPL that `lancedb.connect(tempfile.mkdtemp())` works, and that a `.where("category = 'pm'")` filter returns what you expect. **Ten minutes here saves hours in Phase 2.**

### Phase 2 — RAG engine

Ingestion (PyMuPDF, pandas, TXT, `urls.txt` with timeout and concurrency cap), per-type chunking (§4.2), local embeddings off the event loop, LanceDB with build-then-swap, two-level classifier, duplicate suppression, and the public retrieve interface with **prefer-then-backfill** (§4.4). Independent tests (§11) before any agent work.

### Phase 3 — Agent builder (PM + Financial first)

Shared LangGraph state with reducers. Parent router with validated structured output. PM and Financial agents reading `primary_count` for their live-web decision and returning `used_chunk_ids`. Sequential first, then `Send` parallel fan-out and fan-in merge. Then CapEx and General with the same pattern.

`Send` **parallelism is an optimization, not a feature.** Sequential agents produce the identical answer, just slower. If time gets tight, ship sequential — do not let fan-out debugging cost you the CapEx and General agents, which are visible in the demo in a way that concurrency is not.

### Phase 4 — Formatter

Default JSON from §7.3, with deterministic citation derivation and invalid-id dropping per §7.1. Template loader from `resource` / `out` when files appear. PDF later.

### Phase 5 — API glue

Admin ingest / documents / override / status behind `ADMIN_TOKEN`, with `ALLOWED_INGEST_ROOT` enforcement. Client query + job status per §7.2. CORS. In-memory registry with the active-table pointer. All three timeouts wired. LangSmith env. Single-worker run command documented in the README.

### Phase 6 — One UI

Admin: folder path, token prompt, document table with auto vs effective category, override control. Client: question, timeline from §7.2, response viewer with cross-category evidence marked. Toggle only. Widgets and visual polish later.

Generate `types.ts` from the FastAPI OpenAPI schema, or hand-write it once against §7. Do not let the response shape live in two hand-maintained places.

### Phase 7 — Demo prep

Sample folder with 1–2 PDFs, 1 CSV, 1 TXT, `urls.txt`. **Include at least one deliberately mixed document** (budget + timeline in one file) — that is what proves §4.4 works. Pre-cache 2–3 query results. End-to-end: load folder → PM+financial question → timeline → cited JSON. Fallback video already recorded. Optional LangSmith graph in the demo.

Because `policy` is admin-override-only and wiped on every reload, plan the demo corpus so **General is exercised through** `uncategorized` **documents and ingested** `urls.txt` **content**, not through `policy`.

---



## 11. Tests that must pass

`pytest`. Use a **deterministic fake embedder** (hash-based vectors) for `rag_engine` unit tests — real MiniLM makes retrieval assertions flaky and slow. One integration test uses the real model.

**Ingest**

- Mixed folder (PDF, CSV, TXT, `urls.txt`) → categories, metadata, `failed_files` and `failed_urls` populated for bad inputs.
- CSV chunks never split a row; every chunk repeats the header; `row_start` / `row_end` are correct and contiguous.
- PDF chunks never span a page boundary, so `metadata.page` is always accurate.
- Identical content in two files produces one chunk, not two.
- A document whose content matches no category gets `auto_category = 'uncategorized'`.
- A mixed document (budget + timeline) produces chunks with **both** `financial` and `pm` chunk-level categories.

**Retrieval (replaces the old "PM must not return financial chunks" test)**

- Corpus with ≥`MIN_PRIMARY` `pm` chunks → a PM retrieve returns only `pm` or `web` chunks, all with `cross_category = false`.
- Corpus with 0 `pm` chunks → a PM retrieve still returns chunks, **every one** flagged `cross_category = true`, and `primary_count == 0`.
- `primary_count` reflects in-category hits only, never the backfilled total.

**Lifecycle**

- Reloading the same folder twice does not double the chunk count.
- A reload that fails partway leaves the previously loaded KB intact and queryable.
- A reload issued while a query is in flight does not change that query's results.
- Admin override to `policy` / unmarked applies to every chunk of the document and survives until reload; reload resets to auto-classify. `auto_category` is unchanged by an override.
- Restart → KB empty → admin folder path rebuilds it.

**Agents and API**

- PM-only question activates PM. A finance + timeline question activates PM + Financial in parallel.
- Empty KB blocks the client. Empty question is rejected with no job.
- One agent failure still returns a merged answer from the others; that agent shows `failed` on the timeline.
- An agent exceeding `AGENT_TIMEOUT` is marked failed and does not stall the job.
- A section citing a nonexistent id has that id dropped and a warning added; the job still completes.
- Every `quote` in `citations` is a literal prefix of the corresponding chunk's content.
- `GET /status/` with an unknown id returns 404.
- `/admin/*` without `ADMIN_TOKEN` returns 401. An ingest path outside `ALLOWED_INGEST_ROOT` returns 403.

---



## 12. Demo script (about 3 minutes)

1. Toggle Admin, enter the token, load the sample folder. Show auto tags, including one `uncategorized`. Optionally retag one file as `policy`.
2. Toggle Client. Ask a question that needs both PM and Financial.
3. Show the live agent timeline.
4. Show the cited JSON answer. Point at a citation and note it maps to a real chunk with a verbatim quote.
5. Optional and worth showing: ask something your corpus barely covers, and show cross-category evidence labelled honestly instead of an empty answer.
6. If APIs are up, open LangSmith and show the execution graph.
7. If live APIs fail, show the pre-cached result.

---



## 13. Key decisions and why


| Decision                          | Why                                                                                                             |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Two backend modules + one UI      | RAG can be tested alone. Agents only call `retrieve()`. One app, two modes, instead of two frontends.           |
| FastAPI as glue                   | Holds keys, CORS, and the job registry. Not a third domain package.                                             |
| LanceDB in a temp dir             | Free, no server, no API gamble. Restart behaviour matches the in-memory intent.                                 |
| Local HuggingFace embeddings      | OpenRouter does not provide embeddings. No extra embedding API key.                                             |
| Shared folder ingest              | Clients only ask questions. Admin owns the corpus.                                                              |
| Auto-classify + admin override    | Fast load; admin can mark policy / quick docs. Overrides are disposable in this slice.                          |
| Chunk-level categories            | A charter's budget table is reachable by Financial even though the file reads as PM.                            |
| Prefer-then-backfill retrieval    | A misclassification degrades to labelled off-domain evidence instead of a silent "no evidence found."           |
| Live web keyed on `primary_count` | Preserves "my domain has no docs, go to the web" once backfill exists.                                          |
| Build-then-swap on reload         | The only way to honour "KB unchanged if the previous load succeeded," and it protects in-flight queries.        |
| Parent routes agents              | Not every question needs all four agents. Saves time and tokens.                                                |
| LangGraph `Send`                  | True parallel fan-out in one superstep. Reducers merge results. Droppable under time pressure.                  |
| Formatter as a separate layer     | Final envelope applied once. Also the natural place to derive citations, since it sees every agent's chunk ids. |
| Citations derived, quotes copied  | The model cannot invent a source or paraphrase a quotation.                                                     |
| Default JSON now, templates later | Unblocks the client viewer without waiting on the final schema or PDF style.                                    |
| Admin token + ingest root         | The UI toggle is not a security boundary, and ingest reads arbitrary host paths.                                |
| Single worker                     | KB and jobs are in-process; multiple workers cause intermittent empty-KB reads.                                 |


---



## 14. Gotchas


| Risk                                             | Mitigation                                                                            |
| ------------------------------------------------ | ------------------------------------------------------------------------------------- |
| Hard category filter silently loses evidence     | Prefer-then-backfill with `cross_category` flags (§4.4).                              |
| Classifier forced into a wrong bucket            | `uncategorized` is a legal classifier output.                                         |
| `lancedb.EphemeralClient()` does not exist       | ChromaDB API from the v1.0 docx. Use `lancedb.connect(tempfile.mkdtemp())`.           |
| LanceDB filters are SQL strings, not dicts       | One quoting helper in `vectorstore.py`. Never interpolate raw filenames.              |
| NULL category matches nothing in SQL             | Store the literal `'uncategorized'`. Never NULL.                                      |
| Multiple uvicorn workers → intermittent empty KB | `--workers 1`, no `--reload`.                                                         |
| Embedding blocks the event loop                  | `await asyncio.to_thread(...)` around every embed and search.                         |
| Reload during a live query corrupts it           | Build-then-swap; jobs hold their table handle (§4.3).                                 |
| Reload appends instead of replaces               | New table per ingest, never `add()` onto the live one.                                |
| Parallel agents overwrite shared state           | `Annotated[list, operator.add]` on fields agents write.                               |
| Unbounded LLM or web calls hang the demo         | `LLM_TIMEOUT`, `AGENT_TIMEOUT`, `JOB_TIMEOUT` (§4.6).                                 |
| One slow URL stalls the whole folder load        | `URL_FETCH_TIMEOUT` + `URL_FETCH_CONCURRENCY`.                                        |
| Model invents citation ids or paraphrases quotes | Formatter derives ids from real chunks; `quote` is copied text (§7.1).                |
| CSV chunks split mid-row and lose the header     | Row-bounded chunking, header repeated, `row_start` / `row_end` (§4.2).                |
| Boilerplate crowds out real evidence in `TOP_K`  | Content-hash duplicate suppression at ingest.                                         |
| Router names an agent that is not built yet      | Validate against built agents; fall through to the §9 fallback.                       |
| Admin endpoints are unauthenticated              | `ADMIN_TOKEN` + `ALLOWED_INGEST_ROOT`.                                                |
| No end-to-end path until Phase 5                 | Accepted. Record the fallback video at first success; keep a Phase 2 smoke script.    |
| In-memory KB and jobs die on restart             | Accepted. Admin reloads the folder. Client gets a 404 and asks again.                 |
| Overrides die on reload, so `policy` is empty    | Accepted. Demo General through `uncategorized` + web instead.                         |
| Large CSVs create too many chunks                | Batch 10–50 rows per document.                                                        |
| API keys in the frontend                         | Keys stay in FastAPI `.env` only.                                                     |
| Slow or down live APIs during demo               | Pre-cache 2–3 results. Warnings on the job, do not block.                             |
| LangSmith shows nothing                          | Set `LANGCHAIN_TRACING_V2` and `LANGCHAIN_API_KEY` before start. Tracing is optional. |
| WeasyPrint system deps (later)                   | Docker or ReportLab fallback.                                                         |
| First embedding-model download is slow           | Pre-download during setup.                                                            |
| ChromaDB leftover from the v1.0 docx             | Do not use ChromaDB. LanceDB only.                                                    |
| Flaky retrieval tests                            | Deterministic fake embedder for unit tests.                                           |


---



## 15. Deferred (explicit, not missing)

- Final JSON schema and PDF layout (files under `resource` / `out`).
- PDF download UX and WeasyPrint/ReportLab production path.
- Real login and role-based Admin vs Client (replaces the toggle; `ADMIN_TOKEN` is the interim guard).
- Durable LanceDB.
- Saved classification overrides, and the optional `categories.txt` folder manifest that would make `policy` reproducible across reloads.
- True RAM-resident LanceDB via a `memory://` connection, if it verifies on the installed version.
- Chunk-level classification by LLM rather than heuristic, if the heuristic proves too coarse.
- Widget look-and-feel.
- Finance-lead persona polish (PM + Financial behavior is enough for the first slice).

---



## 16. What you will still provide during implementation

- Sample documents in one folder (1–2 PDFs, 1 CSV, 1 TXT, optional `urls.txt`) for PM and financial questions, **including one deliberately mixed document** so §4.4 is demonstrable.
- Agent prompt details if Financial / PM / CapEx / General need a specific analysis framework.
- Final JSON and PDF templates when ready; drop them into `resource` / `out` without changing agent internals.

