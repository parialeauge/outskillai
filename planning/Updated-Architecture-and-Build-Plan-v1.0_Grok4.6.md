# Multi-Agent AI Deep Researcher — Architecture & Build Plan

Refined from `Updated Architecture & Build Plan_v1.0.docx` after design review. This file is the source of truth for implementation.

**Product:** Admin loads a shared document folder into an in-memory knowledge base. Client users ask a question. A parent agent routes to specialist agents (Financial, PM, CapEx, General). Agents retrieve from category-filtered RAG, optionally search the live web, merge findings, and return a cited answer.

**First slice focus:** PM and Financial agents, folder ingest, Admin | Client toggle UI, default JSON response. CapEx, General, custom templates, PDF, login, and disk persistence follow in later iterations.

---



## 1. Locked decisions


| Topic              | Decision                                                                                                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Backend            | Two modules only: `rag_engine` and `agent_builder`. FastAPI is thin glue, not a third product.                                                                           |
| UI                 | One React + TypeScript app. Header toggle **Admin | Client**. Login and roles replace the toggle later. Look-and-feel / widgets later.                                   |
| Vector DB          | **LanceDB**, in-memory only. After every restart, admin provides a folder path; the app rebuilds the vector DB in RAM.                                                   |
| Who adds documents | Office admin only. One shared knowledge base. Clients never upload.                                                                                                      |
| Folder shape       | One folder. Scan `pdf`, `csv`, `txt`, and `urls.txt`. Auto-classify each file.                                                                                           |
| Categories         | Auto-classify assigns `financial`, `pm`, or `capex`. Only admin can retag as `policy` or clear the tag (unmarked **quick doc**).                                         |
| Overrides          | In memory only. Reload or restart auto-classifies again.                                                                                                                 |
| Client query       | Question text only. No source picker. Parent routes automatically.                                                                                                       |
| Agents             | All four exist and use the same pattern. First build: **PM + Financial**. Then CapEx + General.                                                                          |
| Live web           | General: Tavily/NewsAPI if RAG is thin **or** the question needs current info. Financial / PM / CapEx: tagged docs + ingested URLs; live web **only if RAG is empty**.   |
| Ingested web       | `urls.txt` in the admin folder is ingested as type `web`. URLs are not auto-classified as financial / pm / capex.                                                        |
| Response / PDF     | Custom JSON and PDF templates later, stored under app `resource` / `out`. Until then, use the default JSON shape in this plan. PDF control hidden/disabled.              |
| External services  | Keep OpenRouter, Tavily, NewsAPI, LangSmith. Chat model is `OPENROUTER_MODEL` in `.env` (default: `openai/gpt-4o-mini`). If one service fails, continue with what works. |
| Persistence        | No disk LanceDB and no saved overrides in this slice.                                                                                                                    |


---



## 2. Architecture



### Architecture Diagram

Copied from `Updated Architecture & Build Plan_v1.0.docx`.

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
└──────────────────────────────┘  └────────────────────────────-------──┘
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



### Refined architecture (this plan)

```
[ One React app ]
  toggle: Admin | Client
        |
        | HTTP
        v
[ Thin FastAPI glue ]
  routes, CORS, in-memory job registry, env keys
        |
   +----+----+
   v         v
[ rag_engine ]     [ agent_builder ]
 folder ingest     parent router
 auto-classify     financial / pm / capex / general
 LanceDB RAM       retrieve() + optional live web
 retrieve/clear    merge → formatter → optional PDF later
```

**rag_engine** owns files, chunking, local embeddings, in-memory LanceDB, and `ingest` / `retrieve` / `clear`. It does not call the chat LLM for answers. It may call a small classifier model or heuristic to assign `financial` / `pm` / `capex`.

**agent_builder** owns the parent, four specialist agents, LangGraph parallel fan-out, merge, formatter, and PDF later. It never parses files. It only calls `retrieve()` and external APIs.

**Shared in-process imports.** Both packages run inside the FastAPI process. No HTTP between packages.

### Repository layout

```
outskillai/
├── frontend/                      # One React + TypeScript app
├── apps/api/                      # Thin FastAPI glue
│   ├── main.py
│   ├── routes.py
│   └── session_registry.py        # In-memory KB handle + jobs
├── packages/
│   ├── rag_engine/
│   │   ├── ingestion.py           # PDF / CSV / TXT / urls.txt
│   │   ├── chunker.py
│   │   ├── embeddings.py          # sentence-transformers/all-MiniLM-L6-v2
│   │   ├── classifier.py          # auto: financial | pm | capex
│   │   ├── vectorstore.py         # LanceDB ephemeral
│   │   └── retriever.py           # public ingest / retrieve / clear
│   └── agent_builder/
│       ├── parent_agent.py
│       ├── financial_agent.py
│       ├── pm_agent.py
│       ├── capex_agent.py
│       ├── general_agent.py
│       ├── graph.py
│       ├── state.py
│       ├── formatter.py
│       └── pdf_generator.py       # later
├── shared/
│   ├── config.py
│   └── llm.py                     # OpenRouter wrapper
├── resource/                      # later: JSON / PDF templates
├── out/                           # later: generated reports
└── sample_data/                   # test folder for admin ingest
```

---



## 3. UI — one app, two modes

Look-and-feel and widget styling are out of this slice. Behavior is in scope.

**Shared chrome:** app name, **Admin | Client** toggle, connection/job status. No auth. No per-user history.

### Admin mode

- Folder path field + **Load / Reload**.
- Rebuilds the shared in-memory LanceDB from that folder.
- Document table: filename, auto category (`financial` / `pm` / `capex`), admin override (`policy` or unmarked quick doc).
- Status: last folder, file count, per-file ingest errors.
- Admin does not run research questions in this slice.



### Client mode

- Question box only. No upload. No source picker.
- Submit starts a job. **Agent timeline** updates as agents run.
- **Response viewer** shows the formatted JSON answer.
- PDF download hidden/disabled until a PDF template exists.
- If the shared KB is empty: “Knowledge base not loaded — ask admin.” Do not start a job.

---



## 4. Data flow



### Admin loads the knowledge base

1. Admin pastes a folder path and clicks Load / Reload.
2. `rag_engine` scans `pdf`, `csv`, `txt`, and `urls.txt`.
3. Each file or URL is chunked (~1000 characters, 200 overlap) with source metadata (filename or URL, type, page or row).
4. Files (`pdf` / `csv` / `txt`) are auto-classified as `financial`, `pm`, or `capex`. Entries from `urls.txt` are stored as `type = web` with `category = uncategorized` (not auto-classified). Admin may retag any document as `policy` or unmarked until the next reload.
5. Chunks are embedded with `sentence-transformers/all-MiniLM-L6-v2` and stored in in-memory LanceDB.
6. API returns the shared `knowledge_base_id` (`shared`) and the document list.

CSV rows are batched (about 10–50 rows per document) so large spreadsheets do not explode chunk count.

### Client asks a question

1. Client submits text. API creates a `job_id` and starts `agent_builder`.
2. Parent agent picks one or more specialists. In the first slice it may only pick PM and/or Financial. After CapEx and General are built, it may pick any of the four.
3. Each activated agent:
  - Rewrites a sub-question for its domain.
  - Calls `retrieve(kb_id, sub_question, category=…)`.
  - Optionally calls Tavily/NewsAPI per the live-web rules.
  - Synthesizes findings on OpenRouter with citations.
4. Agents run in parallel via LangGraph `Send`. Fan-in merge uses a reducer (`operator.add`) so parallel writes do not overwrite each other.
5. Formatter applies the default JSON shape (or a template from `resource` / `out` when present).
6. Client polls `GET /status/{job_id}` for timeline updates and the final answer.



### Retrieval rules


| Agent     | RAG filter                                                     | Live web (Tavily / NewsAPI)                                                                 |
| --------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Financial | `category = financial` **or** `type = web`                     | Only if RAG is **empty** (0 chunks)                                                         |
| PM        | `category = pm` **or** `type = web`                            | Only if RAG is **empty** (0 chunks)                                                         |
| CapEx     | `category = capex` **or** `type = web`                         | Only if RAG is **empty** (0 chunks)                                                         |
| General   | `category` is `uncategorized` or `policy`, **or** `type = web` | If RAG is **thin** (fewer than 2 chunks) **or** the parent sets `needs_current_info = true` |


**Empty** means the retrieve call returned 0 chunks. **Thin** means fewer than 2 chunks. Do not use an LLM to decide “usefulness” in this slice.

### Restart

RAM is empty. Admin must provide the folder path again. Classification overrides are gone. In-memory jobs are gone.

---



## 5. Package interface

Agent Builder never touches file parsing, embeddings, or LanceDB internals.

```
ingest(folder_path: str) -> knowledge_base_id   # always the shared KB; id is "shared"

retrieve(
  knowledge_base_id: str,
  query: str,
  top_k: int = 5,
  category: str | list[str] | None = None,
  source_type: str | list[str] | None = None,
) -> list[Chunk]

clear(knowledge_base_id: str) -> bool

list_documents(knowledge_base_id: str) -> list[DocumentInfo]

set_category(knowledge_base_id: str, document_id: str, category: str | None) -> bool
```

`Chunk`:

- `content`: str
- `metadata.source`: filename or URL
- `metadata.type`: `pdf` / `csv` / `txt` / `web`
- `metadata.category`: `financial` / `pm` / `capex` / `policy` / `uncategorized`
- `metadata.page`: int (PDF)
- `metadata.row`: int (CSV)
- `metadata.relevance`: float

`category=None` on `set_category` means unmarked quick doc.

---



## 6. Agents

All four agents follow the same pattern and should be equally capable. They differ only in system prompt, category filter, and live-web rule.


| Agent           | Focus                                                         | Example question                                   |
| --------------- | ------------------------------------------------------------- | -------------------------------------------------- |
| Financial       | Revenue, costs, ROI, financial health, budgets                | “What is the financial impact of this project?”    |
| Project Manager | Timelines, milestones, risks, resource allocation             | “What is the project timeline and key risks?”      |
| CapEx           | Capital expenditures, asset depreciation, investment planning | “What capital investments are needed?”             |
| General         | Unmarked docs, policy, web, leftover questions                | “Summarize the key findings from these documents.” |


Each agent returns structured findings: `summary`, `key_points`, `evidence[]` with source citations.

Parent routing: activate 1–4 agents from the question.

- First slice (only PM + Financial built): pick from those two. If routing fails or the question fits neither, activate **both** so the client still gets an answer.
- After General exists: if routing fails, activate **General** only.

---



## 7. Default response format

Custom JSON will be supplied later and loaded from `resource` / `out`. Until then, every completed job returns this shape:

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
      "quote": "string"
    }
  ],
  "warnings": [],
  "pdf_available": false
}
```

Every claim in `sections` should point at a citation id. The formatter applies this shape once after merge. Agents do not invent the final envelope.

PDF generator (later): WeasyPrint from the formatted output. Include title, date, report id, agent contributions, citations, source table. Only when the user asks and a template exists. Fallback if WeasyPrint system deps are missing: ReportLab.

---



## 8. API layer


| Endpoint                      | Purpose                                                                                                |
| ----------------------------- | ------------------------------------------------------------------------------------------------------ |
| `POST /admin/ingest`          | Body: `{ "folder_path": "..." }`. Ingest folder, return `knowledge_base_id` + document list.           |
| `GET /admin/documents`        | List documents and categories for the shared KB.                                                       |
| `PATCH /admin/documents/{id}` | Body: `{ "category": "policy" | "uncategorized" | "financial" | "pm" | "capex" }`. In-memory override. |
| `GET /admin/status`           | Whether a KB is loaded, last folder, file counts, errors.                                              |
| `POST /query`                 | Body: `{ "query": "..." }`. Uses the shared KB. Returns `job_id`.                                      |
| `GET /status/{job_id}`        | Job status, agent timeline, partial/final result.                                                      |
| `GET /report/{job_id}/pdf`    | Later. Hidden until PDF template exists.                                                               |


Session / job registry is an in-memory dict for this slice. Track: shared KB handle, document list, overrides, running jobs, completed results.

CORS is enabled for the React app.

LangSmith: `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` in `.env`. Tracing must never block an answer.

`.env` keys: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (default `openai/gpt-4o-mini`), `TAVILY_API_KEY`, `NEWSAPI_API_KEY`, `LANGSMITH_API_KEY` / `LANGCHAIN_API_KEY`, embedding model name.

---



## 9. Errors and empty states

**Knowledge base**

- Empty or missing folder → Admin sees a clear error. KB stays empty (or unchanged if a previous load succeeded).
- Unreadable file → skip it, list it as failed, continue the rest.
- Bad URL in `urls.txt` → skip that URL, list it as failed.
- After restart, KB is empty until Admin loads a folder. Client cannot start a job.

**Query / agents**

- Empty question → reject, no job.
- Parent routing fails → first slice: activate both PM and Financial. After General exists: General only.
- One specialist fails → job continues; that agent is `failed` on the timeline; merge uses the others.
- All agents fail → job status `failed` with a short reason. No fabricated answer.
- Specialist RAG empty (0 chunks) → that agent may call live web. If live web also fails, return “no evidence found.”
- OpenRouter / Tavily / NewsAPI / LangSmith down → continue with what works; add a warning on the job.

**Response / PDF**

- No custom template → default JSON. Do not fail the job.
- PDF not ready → client control hidden/disabled.

**Jobs**

- Server restart drops jobs. Client is told the job is gone and can ask again.

---



## 10. Build plan



### Phase 1 — Setup

Create the monorepo layout, Python venv, shared config, OpenRouter wrapper, `.env`, and frontend shell with the Admin | Client toggle.

### Phase 2 — RAG engine (first)

Ingestion (PyMuPDF, pandas, TXT, `urls.txt` / WebBaseLoader), chunking, local embeddings, LanceDB ephemeral, auto-classifier, public retrieve interface with category filter. Independent tests before any agent work.

Pre-download the embedding model on setup so first run is not a surprise:

`python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"`

### Phase 3 — Agent builder (PM + Financial first)

Shared LangGraph state with reducers. Parent router. PM and Financial agents. Sequential first, then `Send` parallel fan-out and fan-in merge. Then CapEx and General with the same pattern.

### Phase 4 — Formatter

Default JSON from section 7. Template loader from `resource` / `out` when files appear. PDF later.

### Phase 5 — API glue

Admin ingest / documents / override / status. Client query + job status. CORS. In-memory registry. LangSmith env.

### Phase 6 — One UI

Admin: folder path, table, override. Client: question, timeline, response viewer. Toggle only. Widgets / visual polish later.

### Phase 7 — Demo prep

Sample folder with 1–2 PDFs, 1 CSV, 1 TXT, `urls.txt`. Pre-cache 2–3 query results. End-to-end: load folder → PM+financial question → timeline → JSON. Record a fallback video. Optional LangSmith graph in the demo.

---



## 11. Tests that must pass

- Mixed folder ingest (PDF, CSV, TXT, `urls.txt`) → categories, metadata, skipped bad files listed.
- `retrieve` for `pm` does not return `financial` chunks (and the reverse).
- Admin override to `policy` / unmarked works until reload; reload resets to auto-classify.
- PM-only question activates PM. A finance + timeline question activates PM + Financial in parallel.
- Empty KB blocks the client.
- One agent failure still returns a merged answer from the others.
- Restart → RAM empty → admin folder path rebuilds the KB.

---



## 12. Demo script (about 3 minutes)

1. Toggle Admin. Load the sample folder. Show auto tags. Optionally retag one file.
2. Toggle Client. Ask a question that needs both PM and Financial.
3. Show the live agent timeline.
4. Show the cited JSON answer.
5. If APIs are up, open LangSmith and show the execution graph.
6. If live APIs fail, show a pre-cached result.

---



## 13. Key decisions and why


| Decision                          | Why                                                                                                   |
| --------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Two backend modules + one UI      | RAG can be tested alone. Agents only call `retrieve()`. One app, two modes, instead of two frontends. |
| FastAPI as glue                   | Holds keys, CORS, and the job registry. Not a third domain package.                                   |
| LanceDB in memory                 | Free, no server, enough for the hackathon. Admin reload after restart is accepted.                    |
| Local HuggingFace embeddings      | OpenRouter does not provide embeddings. No extra embedding API key.                                   |
| Shared folder ingest              | Clients only ask questions. Admin owns the corpus.                                                    |
| Auto-classify + admin override    | Fast load; admin can mark policy / quick docs. Overrides are disposable in this slice.                |
| Parent routes agents              | Not every question needs all four agents. Saves time and tokens.                                      |
| LangGraph `Send`                  | True parallel fan-out in one superstep. Reducers merge results.                                       |
| Formatter as a separate layer     | Final envelope is applied once. Agents return findings, not the full response schema.                 |
| Default JSON now, templates later | Unblocks the client viewer without waiting on the final schema or PDF style.                          |


---



## 14. Gotchas


| Risk                                   | Mitigation                                                                            |
| -------------------------------------- | ------------------------------------------------------------------------------------- |
| Parallel agents overwrite shared state | `Annotated[list, operator.add]` (or equivalent reducer) on fields agents write.       |
| In-memory KB and jobs die on restart   | Accepted. Admin reloads the folder. Client is told the job is gone.                   |
| Classification overrides die on reload | Accepted for this slice. Document it in the Admin UI.                                 |
| Large CSVs create too many chunks      | Batch 10–50 rows per document.                                                        |
| API keys in the frontend               | Keys stay in FastAPI `.env` only.                                                     |
| Slow or down live APIs during demo     | Pre-cache 2–3 results. Warnings on the job, do not block.                             |
| LangSmith shows nothing                | Set `LANGCHAIN_TRACING_V2` and `LANGCHAIN_API_KEY` before start. Tracing is optional. |
| WeasyPrint system deps (later)         | Docker or ReportLab fallback.                                                         |
| Parent activates the wrong agents      | Test with PM-only, finance-only, and mixed questions. Refine the routing prompt.      |
| First embedding-model download is slow | Pre-download during setup.                                                            |
| ChromaDB leftover from the v1.0 docx   | Do not use ChromaDB. LanceDB only.                                                    |


---



## 15. Deferred (explicit, not missing)

- Final JSON schema and PDF layout (files under `resource` / `out`).
- PDF download UX and WeasyPrint/ReportLab production path.
- Real login and role-based Admin vs Client (replace the toggle).
- Disk-persisted LanceDB.
- Saved classification overrides (sidecar or folder manifest).
- Widget look-and-feel.
- Finance-lead persona polish (PM + Financial behavior is enough for the first slice).

---



## 16. What you will still provide during implementation

- Sample documents in one folder (1–2 PDFs, 1 CSV, 1 TXT, optional `urls.txt`) for PM and financial questions.
- Agent prompt details if Financial / PM / CapEx / General need a specific analysis framework.
- Final JSON and PDF templates when ready; drop them into `resource` / `out` without changing agent internals.

