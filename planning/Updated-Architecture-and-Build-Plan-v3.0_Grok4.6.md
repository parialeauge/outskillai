# Pactlify — Architecture & Build Plan (v3.0)

Supersedes `Updated-Architecture-and-Build-Plan-Opus5.md`. **This file is the source of truth for implementation.** Opus5 and earlier planning files are history.

**Product:** Pactlify. Admin loads a shared document folder into an in-memory knowledge base. Client users ask a question. A parent agent routes to specialist agents (Financial, PM, CapEx, General). Agents retrieve from category-preferring RAG, optionally search the live web, merge findings, and return a cited answer. The UI is one React app with three screens: mosaic landing, mosaic Client workspace, pastel Admin workspace.

**First slice focus:** PM and Financial agents, folder ingest with optional category stamp, three-route UI (landing / client / admin), default JSON response, minimal PDF download. CapEx, General, custom templates, real login, and disk persistence follow in later iterations.

**What changed from Opus5 (v1.x of this line).** The product is named **Pactlify**. Look-and-feel is now in scope: [Mosaic Grid Architecture](https://superdesign.dev/library?category=style&selected=mosaic-grid-architecture-style) for landing + Client, [Promptly FAQ card-grid-pastel](https://superdesign.dev/library?category=all&selected=promptly-faq-card-grid-pastel&search=two+pannet) for Admin body. Routes are `/`, `/client`, `/admin`. Admin category cards are an optional single-select stamp; none selected means auto-detect. After ingest, a document table (id, name, category) is filled from `list_documents` plus a session `documentStore`. Client right pane is tabbed **Answer | Timeline | Sources** with a real **Download PDF** control. Backend retrieval, agents, and contracts from Opus5 are unchanged except optional `category` on ingest and a minimal PDF in this slice.

Backend carry-forward from Opus5 (still locked): category filtering is *preference with flagged backfill* (§4.4). The classifier may return `uncategorized`. Reload is build-then-swap. LanceDB uses a temp directory, not `EphemeralClient()`. Timeouts, `ADMIN_TOKEN`, and the job-status contract stay as specified. Phase order is unchanged.

---



## 1. Locked decisions


| Topic                      | Decision                                                                                                                                                                                                                                                                                                      |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Name                       | **Pactlify.** Wordmark in the header; clicking it returns to `/`.                                                                                                                                                                                                                                             |
| Backend                    | Two modules only: `rag_engine` and `agent_builder`. FastAPI is thin glue, not a third product.                                                                                                                                                                                                                |
| UI                         | One React + TypeScript app. Three routes: `/` landing, `/client`, `/admin`. Shared header: **Pactlify** + **Admin | Client** toggle + KB/job chip. Login and roles replace the toggle later.                                                                                                                  |
| Visual systems             | Landing + Client: Mosaic Grid Architecture (forest `#1A3C2B`, paper `#F7F7F5`, Space Grotesk + JetBrains Mono, bento, zero shadows). Admin **body**: Promptly pastel card-grid (peach canvas, white rounded cards, colored dots). Header stays mosaic on all pages.                                           |
| Vector DB                  | **LanceDB**, per-process temp directory, discarded on exit. After every restart, admin provides a folder path; the app rebuilds the vector DB.                                                                                                                                                                |
| Process model              | **Single worker.** `uvicorn --workers 1`, no `--reload`. The KB and job registry are in-process state.                                                                                                                                                                                                        |
| Who adds documents         | Office admin only. One shared knowledge base. Clients never upload.                                                                                                                                                                                                                                           |
| Folder shape               | One folder. Scan `pdf`, `csv`, `txt`, and `urls.txt`.                                                                                                                                                                                                                                                         |
| Categories                 | Optional **pre-ingest stamp**. No card selected → auto-classify each file as `financial` / `pm` / `capex` / `uncategorized`. One card selected → every file (and `urls.txt` entries) in that Submit is stamped with that category (`financial` / `pm` / `capex` / `policy`). Auto-detect remains the default. |
| Classification granularity | Per **document** (shown in the admin table) **and** per **chunk** (used for retrieval). See §4.2.                                                                                                                                                                                                             |
| Overrides                  | In memory only. Reload or restart auto-classifies again unless the admin re-stamps.                                                                                                                                                                                                                           |
| Client query               | Question text only. No source picker. Parent routes automatically. Right pane tabs: **Answer | Timeline | Sources**.                                                                                                                                                                                          |
| Agents                     | All four exist and use the same pattern. First build: **PM + Financial**. Then CapEx + General.                                                                                                                                                                                                               |
| Retrieval filtering        | **Preference, not exclusion.** An agent's category is preferred; if it yields fewer than `MIN_PRIMARY` chunks, the shortfall is backfilled from the rest of the KB and flagged `cross_category`.                                                                                                              |
| Live web                   | Triggered on the **primary** (in-category) result only, never on the backfilled total. General: if primary is thin **or** the question needs current info. Financial / PM / CapEx: only if primary is empty.                                                                                                  |
| Ingested web               | `urls.txt` is type `web`. Auto-detect ingest: category `uncategorized` (not classified as financial / pm / capex). Stamped ingest: URLs take the selected category.                                                                                                                                           |
| Response / PDF             | Default JSON shape in §7. **Download PDF** is a first-slice Client control, enabled when the job is `completed`. Minimal PDF is generated from that envelope. Custom JSON/PDF templates later under `resource` / `out`.                                                                                       |
| Citations                  | Derived by the formatter from chunks actually retrieved. Agents never mint citation ids. `quote` is copied from chunk text, never model-written.                                                                                                                                                              |
| Admin endpoints            | Guarded by `ADMIN_TOKEN`. Ingest paths must resolve under `ALLOWED_INGEST_ROOT`.                                                                                                                                                                                                                              |
| External services          | Keep OpenRouter, Tavily, NewsAPI, LangSmith. Chat model is `OPENROUTER_MODEL` in `.env` (default: `openai/gpt-4o-mini`). If one service fails, continue with what works.                                                                                                                                      |
| Persistence                | No durable LanceDB and no saved overrides in this slice. Document table uses the in-process document list plus a client `documentStore` for the session.                                                                                                                                                      |


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
[ Pactlify — one React app ]
  chrome: wordmark + Admin | Client toggle + KB/job chip
  /            mosaic landing
  /client      mosaic two-panel (search | Answer/Timeline/Sources + PDF)
  /admin       pastel stack (category cards -> upload -> document table)
        |
        | HTTP  (admin routes carry ADMIN_TOKEN)
        v
[ Thin FastAPI glue ]  -- single worker
  routes, CORS, in-memory job registry + document list, env keys
        |
   +----+----+
   v         v
[ rag_engine ]     [ agent_builder ]
 folder ingest     parent router
 optional stamp    financial / pm / capex / general
 or auto-classify  retrieve() + optional live web
 doc + chunk tags  merge -> formatter -> minimal PDF
 LanceDB (tmpdir)  citations derived here
 retrieve/clear
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
├── frontend/                      # One React + TypeScript app — Pactlify
│   └── src/
│       ├── types.ts               # Mirrors §7 + §7.2 (or generated from OpenAPI)
│       ├── stores/documentStore.ts
│       ├── theme/mosaic.css
│       ├── theme/pastel.css
│       └── pages/                 # Landing, Client, Admin
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



## 3. UI — Pactlify, three screens

Look-and-feel is **in scope**. One app, three routes, two visual systems, one chrome. No per-user history.

References:

- Landing + Client: [Mosaic Grid Architecture Style](https://superdesign.dev/library?category=style&selected=mosaic-grid-architecture-style)
- Admin body: [Promptly FAQ card-grid-pastel](https://superdesign.dev/library?category=all&selected=promptly-faq-card-grid-pastel&search=two+pannet)



### 3.1 Shared chrome

Present on `/`, `/client`, and `/admin`.


| Slot         | Content                                                                                                                                                                                                     |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Left         | Wordmark **Pactlify** → `/`                                                                                                                                                                                 |
| Center-right | Segmented toggle **Admin | Client**. Sets the mode and navigates to `/admin` or `/client`.                                                                                                                  |
| Far right    | Status chip: `KB empty` / `KB loaded · N docs` / `Job running`. KB counts come from public `GET /kb` (loaded flag + count only — no folder path, no filenames). Job text comes from the active client poll. |


The toggle is UI convenience, **not** a security boundary. Admin API calls still require `ADMIN_TOKEN` in memory for the session.

### 3.2 Design tokens

**Mosaic (landing, Client, header on every page)**

- Paper background `#F7F7F5`, forest `#1A3C2B`, ink on paper
- Space Grotesk for display and UI; JetBrains Mono for labels, ids, status, citation chips
- Bento / mosaic grid, 1px hairline borders, **zero shadows**, 2D flat wireframe feel
- Primary button: forest fill, paper type

**Pastel (Admin body only)**

- Pale peach / off-white canvas
- White cards, ~20px radius, thin light border, soft shadow
- Bold dark title, gray description, colored dot top-right
- Selected card: thicker tinted border (no second “selected” language on the card)

Do not mix pastel cards into Client, and do not apply mosaic hairlines to Admin category cards.

### 3.3 Landing — `/`

Mosaic hero + bento. Empty KB is allowed; this page never starts a job.

1. Hero band: mono label `MULTI-AGENT RESEARCH`, headline, one-line pitch. Example: *Pactlify — ask the corpus; specialists cite what they used.*
2. Mosaic tiles:
  - Large **Ask the corpus** → `/client`
  - **Load documents** → `/admin`
  - Four non-link agent tiles: Financial, PM, CapEx, General
  - Status tile repeating KB state
3. Footer strip: admin loads a folder; clients only ask. No upload here.



### 3.4 Client — `/client`

Mosaic two-panel. No upload, no source picker, no category cards.

**Left pane (~36%) — search only**

- Mono label `QUERY`
- Multi-line question field
- **Ask** (forest primary)
- Helper: “Parent routes to Financial, PM, CapEx, General.”
- Empty KB: Ask disabled; *Knowledge base not loaded — ask admin.*
- Empty question: reject, no job
- Submitted text stays in the field for edit-and-ask-again. No history list.

**Right pane (~64%) — tabbed result**

Tabs: **Answer | Timeline | Sources**. A mono job status (`routing` / `running` / `merging` / `completed` / `failed`) sits above the tabs. Poll `GET /status/{job_id}` about every 1s. The user may open Timeline while the job runs.

**Answer**

- Formatted from the §7.3 envelope: summary, then one block per activated agent (title, body, key points, citation chips `[c1]`).
- Cross-category citations get a hairline `CROSS` badge.
- **Download PDF** top-right of this tab. Enabled only when `status = completed` **and** `result.pdf_available === true`. Then `GET /report/{job_id}/pdf` as a blob download named `pactlify-{job_id}.pdf`.

**Timeline**

- One row per activated agent from the §7.2 payload: name, status (`pending | retrieving | searching_web | synthesizing | done | failed`), `chunks_retrieved`, `primary_count`, `used_live_web`, error.
- One failed agent does not hide the others.

**Sources**

- Citation rows: id, source, type, category, page or `row_start`/`row_end`, verbatim `quote`, `CROSS` if backfilled.
- Clicking a chip on Answer switches to Sources and highlights that row.

**Client errors**

- Status `404`: *Job no longer available — please ask again.*
- Job `failed`: short reason, no fabricated answer, PDF stays disabled.
- `warnings[]` render as a slim banner above the tabs.



### 3.5 Admin — `/admin`

Header stays mosaic. Body is pastel. Admin does not run research questions.

First visit: prompt once for `ADMIN_TOKEN` and hold it in session memory. `401` stays on the page.

**Category cards (top, 3-column grid)** — optional single-select picker. Cards do not list files.


| Card                   | Dot      | Stamp                                             |
| ---------------------- | -------- | ------------------------------------------------- |
| Financial              | coral    | `financial`                                       |
| Project Manager        | sky      | `pm`                                              |
| CapEx                  | mint     | `capex`                                           |
| Policy                 | lavender | `policy`                                          |
| Auto-detect / unmarked | gray     | none (default visual; equivalent to no selection) |


- Click a card to select; click again to clear.
- **Nothing selected = auto-detect** each file.
- One card selected = every document in that Submit is stamped with that category. Classifier is skipped for that batch: `auto_category = category = stamp`, `overridden = true`.

**Upload panel (below, full width)**

- Folder path field. Submit reads that path on the server under `ALLOWED_INGEST_ROOT` and loads all `pdf` / `csv` / `txt` / `urls.txt`.
- Browser file-drop is not a substitute for the server path in this slice; the contract is `{ "folder_path": "...", "category": <optional> }`.
- **Submit** → `POST /admin/ingest`. Reload **replaces** the shared KB (build-then-swap, §4.3).
- Visible note: table and stamps are in-memory; restart requires the path again.

**Document table (below upload)**

Columns required: **id**, **name**, **category** (effective). Optional extras: type, chunk count, auto vs overridden. Map `document_id` → id, `source` → name, `category` → category. Do not rename those fields on the wire.

- Hydrate on mount from `GET /admin/status` (last folder, last failures) plus `GET /admin/documents` (rows). After Submit, use the ingest response; do not require a second list call (a refresh of both is still allowed).
- Client `documentStore` (`frontend/src/stores/documentStore.ts`) keeps the last successful list for the session so toggling away and back does not flash empty. Server list is the source of truth.
- Empty: *No documents loaded.*
- `failed_files` / `failed_urls` render as a short error list under the table, never as success rows.
- First slice: table is read-only. `PATCH /admin/documents/{id}` remains available for a later row-level retag; it is not required for the demo.

**Admin errors**

- Empty/missing folder, or path outside `ALLOWED_INGEST_ROOT` → message; previous KB unchanged.
- Missing/wrong token → `401`.
- Unreadable file / bad URL → skip, list below the table, continue.



### 3.6 Frontend layout

```
frontend/src/
├── App.tsx                 # chrome + routes
├── api.ts                  # the only HTTP client; mirrors §3.7 + §8
├── pages/Landing.tsx
├── pages/Client.tsx
├── pages/Admin.tsx
├── stores/documentStore.ts # session copy of DocumentInfo[] + last ingest meta
├── theme/mosaic.css
├── theme/pastel.css
└── types.ts
```



### 3.7 Frontend ↔ API map (source of truth)

Every UI action calls exactly one of these. No other HTTP endpoints exist in this slice. `PATCH /admin/documents/{id}` is implemented on the backend and **not called** by the first-slice UI.

Base URL: `VITE_API_BASE_URL` (default `http://localhost:8000`). JSON request/response `Content-Type: application/json` except the PDF download.

Admin auth header (every `/admin/*` call):

```
Authorization: Bearer <ADMIN_TOKEN>
```

The token is prompted once, held in memory for the tab session, never sent on `/kb`, `/query`, `/status/*`, or `/report/*`.

Shared error body (all 4xx):

```json
{ "error": "error_code", "message": "human-readable string" }
```


| UI surface                   | When                                                   | Call                                            | Success                                                                                              | UI on failure                                                                    |
| ---------------------------- | ------------------------------------------------------ | ----------------------------------------------- | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Chrome + Landing status tile | Mount, after ingest success, every ~5s                 | `GET /kb`                                       | `{ loaded, document_count }`                                                                         | Chip shows `KB empty` if the call fails                                          |
| Admin first visit            | Before any `/admin/*`                                  | none (local prompt)                             | token in memory                                                                                      | —                                                                                |
| Admin mount                  | After token                                            | `GET /admin/status` then `GET /admin/documents` | hydrate path field, failures, table                                                                  | `401` → re-prompt token; empty list → *No documents loaded.*                     |
| Admin Submit                 | Click Submit                                           | `POST /admin/ingest`                            | replace `documentStore` + table from `documents`; show `failed_*` under the table; refresh `GET /kb` | `401` re-prompt; `403` path rejected; `400` folder error; previous table/KB stay |
| Admin table columns          | Render                                                 | map only                                        | `id` ← `document_id`; `name` ← `source`; `category` ← `category`                                     | —                                                                                |
| Client Ask enable            | Mount + `GET /kb`                                      | `GET /kb`                                       | Ask enabled iff `loaded === true`                                                                    | Ask stays disabled                                                               |
| Client Ask                   | Click Ask                                              | `POST /query`                                   | start polling `job_id`                                                                               | `400 empty_query` inline; `409 kb_empty` disable Ask                             |
| Client tabs                  | After Ask, every ~1s                                   | `GET /status/{job_id}`                          | render status, timeline, result                                                                      | `404` → *Job no longer available — please ask again.*                            |
| Download PDF                 | Answer tab, job `completed` and `result.pdf_available` | `GET /report/{job_id}/pdf`                      | save blob as `pactlify-{job_id}.pdf`                                                                 | stay disabled; do not invent a PDF                                               |


**Ingest is synchronous.** There is no ingest job id. The Admin Submit button shows a spinner and the frontend uses a **300s** request timeout. Until the response returns, `GET /kb` still reflects the previous KB (build-then-swap).

**Auto-detect card / no card selected:** omit `category` from the ingest body. Do **not** send `"uncategorized"` — that would stamp every file unmarked and skip the classifier.

`documentStore` **holds:** `documents: DocumentInfo[]`, `failed_files`, `failed_urls`, `last_folder`. Replaced on successful ingest. Cleared if `GET /admin/documents` returns an empty `documents` array after a restart.

---



## 4. Data flow



### 4.1 Admin loads the knowledge base

1. Admin optionally selects a category card, pastes a folder path, and clicks Submit. Request carries `ADMIN_TOKEN` and optional `category`.
2. API resolves the path and rejects anything outside `ALLOWED_INGEST_ROOT`.
3. `rag_engine` scans `pdf`, `csv`, `txt`, and `urls.txt`.
4. Each file or URL is chunked per §4.2 with source metadata.
5. **If** `category` **is present:** skip the classifier. Every chunk of every file and every `urls.txt` entry gets `auto_category = category = <stamp>` and `overridden = true`. **If** `category` **is omitted:** classify per §4.2; `urls.txt` stays `uncategorized`.
6. Chunks are embedded with `sentence-transformers/all-MiniLM-L6-v2`.
7. Rows are written to a **new** table; the active pointer swaps only on success (§4.3).
8. API returns the shared `knowledge_base_id` (`shared`) and the document list, including failures. The Admin table and `documentStore` replace their rows from this list.

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

The temp directory is gone. Admin must provide the folder path again. Classification overrides are gone. In-memory jobs are gone. `GET /kb` reports empty. The client `documentStore` must clear when `GET /admin/documents` returns an empty list after a restart.

---



## 5. Package interface

Agent Builder never touches file parsing, embeddings, or LanceDB internals.

```
ingest(folder_path: str, category: str | None = None) -> IngestResult
    # always the shared KB; id is "shared"
    # category stamps the whole batch; None = auto-classify

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

`DocumentInfo`: `document_id`, `source`, `type`, `chunk_count`, `auto_category`, `category`, `overridden: bool`. The Admin table maps `document_id` → **id**, `source` → **name**, `category` → **category**. HTTP `GET /admin/documents` wraps the list as `{ "documents": [...] }`; the Python function still returns a bare list.

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
  "error": null,
  "result": null
}
```

`result` is `null` until `status = "completed"`, then it holds the §7.3 envelope. `error` is `null` unless `status = "failed"`, then it is a short reason (no fabricated answer). An unknown `job_id` returns **404** with `{ "error": "job_not_found", "message": "..." }`, which the client reads as "lost to restart" (§3).

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
  "pdf_available": true
}
```

Every claim in `sections` points at a citation id, enforced per §7.1. The formatter applies this shape once after merge. Agents do not invent the final envelope.

`cross_category: true` on a citation must be visible in the UI. It is the difference between "your PM documents say this" and "no PM document covered it, so here is related material."

**PDF generator (this slice, minimal):** After format, render a simple PDF from the §7.3 envelope: title **Pactlify**, date, job id, query, summary, agent sections, citations, source table. Prefer WeasyPrint; if system deps are missing, ReportLab. Set `pdf_available = true` on `completed`. Custom layout files under `resource` / `out` still come later and replace this renderer without changing agents.

---



## 8. API layer

Frontend call map is §3.7. This section is the wire contract. Auth on `/admin/*` is the header `Authorization: Bearer <ADMIN_TOKEN>` (the raw token, not a login JWT). CORS allows that header from the React origin.


| Endpoint                      | Auth   | Caller                  | Purpose                                                                       |
| ----------------------------- | ------ | ----------------------- | ----------------------------------------------------------------------------- |
| `GET /kb`                     | none   | Chrome, Landing, Client | `{ "loaded": bool, "document_count": int }`. No folder path, no filenames.    |
| `GET /admin/status`           | Bearer | Admin mount             | Last folder, counts, last ingest failures.                                    |
| `GET /admin/documents`        | Bearer | Admin mount             | `{ "documents": DocumentInfo[] }`. Empty KB → `200` with `[]`, not 404.       |
| `POST /admin/ingest`          | Bearer | Admin Submit            | Synchronous folder ingest. Optional `category` stamp. Returns `IngestResult`. |
| `PATCH /admin/documents/{id}` | Bearer | **none in this slice**  | Row retag. Backend must exist; UI does not call it yet.                       |
| `POST /query`                 | none   | Client Ask              | `{ "query": "..." }` → `{ "job_id": "..." }`.                                 |
| `GET /status/{job_id}`        | none   | Client poll             | §7.2 payload.                                                                 |
| `GET /report/{job_id}/pdf`    | none   | Download PDF            | `application/pdf` bytes.                                                      |




### 8.1 Request / response shapes

`GET /kb` → `200`

```json
{ "loaded": false, "document_count": 0 }
```

`loaded` is true only after a successful ingest swap. `document_count` is `0` when `loaded` is false. Must match `GET /admin/status` for the same process.

`GET /admin/status` → `200`

```json
{
  "loaded": true,
  "last_folder": "/allowed/sample_data",
  "document_count": 4,
  "chunk_count": 87,
  "failed_files": [{ "name": "bad.pdf", "reason": "unreadable" }],
  "failed_urls": [{ "url": "https://example.invalid", "reason": "timeout" }]
}
```

Empty KB: `loaded: false`, `last_folder: null`, counts `0`, failure arrays `[]`. `401` if the bearer token is missing or wrong.

`GET /admin/documents` → `200`

```json
{
  "documents": [
    {
      "document_id": "doc_…",
      "source": "charter.pdf",
      "type": "pdf",
      "chunk_count": 12,
      "auto_category": "pm",
      "category": "pm",
      "overridden": false
    }
  ]
}
```

`POST /admin/ingest` — synchronous, frontend timeout 300s.

```json
{ "folder_path": "/allowed/sample_data", "category": "financial" }
```

Omit `category` or send `null` for auto-detect. Allowed values when present: `financial` | `pm` | `capex` | `policy`.

`200` body is `IngestResult`:

```json
{
  "knowledge_base_id": "shared",
  "documents": [],
  "failed_files": [],
  "failed_urls": [],
  "chunk_count": 0
}
```

`documents` uses the same `DocumentInfo` as `GET /admin/documents`. Partial file/URL failures still return `200` if the new table swapped; those rows are only in `failed_*`, never in `documents`.


| Status | `error`          | When                                                                                        |
| ------ | ---------------- | ------------------------------------------------------------------------------------------- |
| 400    | `bad_folder`     | Missing path, folder does not exist, or no `pdf`/`csv`/`txt`/`urls.txt` to ingest. No swap. |
| 401    | `unauthorized`   | Missing/wrong bearer token.                                                                 |
| 403    | `forbidden_path` | Path outside `ALLOWED_INGEST_ROOT`. No ingest attempted.                                    |


`POST /query`

```json
{ "query": "What is the project timeline and financial impact?" }
```

Trim whitespace. `200` → `{ "job_id": "…" }`.


| Status | `error`       | When                                                                     |
| ------ | ------------- | ------------------------------------------------------------------------ |
| 400    | `empty_query` | Empty after trim. No job.                                                |
| 409    | `kb_empty`    | No swapped KB. Message: `Knowledge base not loaded — ask admin.` No job. |


`GET /status/{job_id}` → `200` §7.2, or `404` `{ "error": "job_not_found", "message": "…" }`.

`GET /report/{job_id}/pdf` → `200` with `Content-Type: application/pdf` and `Content-Disposition: attachment; filename="pactlify-{job_id}.pdf"`. `404` `{ "error": "pdf_not_ready", "message": "…" }` if the job is unknown, not `completed`, or `pdf_available` is false.

`PATCH /admin/documents/{id}` (backend only this slice)

```json
{ "category": "policy" }
```

`200` `{ "ok": true, "document": DocumentInfo }`. `404` if that `document_id` is not in the active KB. Same auth as other admin routes.

**Why the admin routes are guarded.** The Admin | Client toggle is client-side UI state, not a security boundary. Without a token, `POST /admin/ingest` lets anyone who can reach the API make the server read an **arbitrary filesystem path** — `../../` walks anywhere the process can read, and that content comes straight back out through `GET /admin/documents` and through answers. On a laptop this is theoretical; it stops being theoretical the moment this runs on a shared network or a box for judging. Two env vars close it, and neither conflicts with real login later.

Session / job registry is an in-memory dict: active KB table pointer, document list, overrides, running jobs, completed results.

**Run single-worker.** With `--workers 2`, admin ingests into worker A while the client's query lands on worker B and sees an empty knowledge base — *intermittently*, depending on which worker gets the request. That is a brutal thing to debug late. Put it in the run command: `uvicorn apps.api.main:app --workers 1`. No `--reload` during a demo, since a reload wipes the KB.

CORS is enabled for the React app.

LangSmith: `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` in `.env`. Tracing must never block an answer.

`.env` keys: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (default `openai/gpt-4o-mini`), `TAVILY_API_KEY`, `NEWSAPI_API_KEY`, `LANGSMITH_API_KEY` / `LANGCHAIN_API_KEY`, `EMBEDDING_MODEL`, `ADMIN_TOKEN`, `ALLOWED_INGEST_ROOT`.

---



## 9. Errors and empty states

**Knowledge base**

- Empty or missing folder → `400 bad_folder`. KB stays empty, or unchanged if a previous load succeeded (guaranteed by build-then-swap, §4.3).
- Path outside `ALLOWED_INGEST_ROOT` → `403 forbidden_path`, no ingest attempted.
- Missing or wrong `ADMIN_TOKEN` → `401 unauthorized`.
- Unreadable file → skip it, list it in `failed_files`, continue the rest.
- Bad or slow URL in `urls.txt` → skip after `URL_FETCH_TIMEOUT`, list it in `failed_urls`.
- Classifier LLM unavailable → fall back to the keyword heuristic; if that is inconclusive, `uncategorized`. Ingest never fails because classification failed.
- After restart, KB is empty until Admin loads a folder. Client cannot start a job.

**Query / agents**

- Empty question → `400 empty_query`, no job.
- KB not loaded → `409 kb_empty`, no job. Message matches the Client empty-KB copy.
- Parent routing fails, or names an agent that is not built → first slice: activate both PM and Financial. After General exists: General only.
- One specialist fails or exceeds `AGENT_TIMEOUT` → job continues; that agent is `failed` on the timeline; merge uses the others.
- All agents fail → job status `failed` with a short reason. **No fabricated answer.**
- Primary retrieval empty → backfill supplies cross-category evidence, and the agent may call live web per §4.4. If both are empty, the agent reports "no evidence found."
- `JOB_TIMEOUT` exceeded → format whatever completed, add a warning, mark `completed`. Never leave a job `running`.
- OpenRouter / Tavily / NewsAPI / LangSmith down → continue with what works; add a warning on the job.

**Response / PDF**

- No custom template → default JSON. Do not fail the job.
- Invented citation id → dropped, warning added (§7.1). Do not fail the job.
- PDF not ready (job not `completed`, or generator failed) → **Download PDF** stays visible and disabled. Add a warning if generation failed; do not fail the job.

**Jobs**

- Server restart drops jobs. `GET /status/{job_id}` returns `404` and the client offers to ask again.

---



## 10. Build plan

Phase order is unchanged from the previous plan: the RAG engine is completed and tested before agent work begins.

**Accepted risk.** With horizontal phases there is no end-to-end path until Phase 5–6, so integration bugs all surface late and there is no fallback demo before then. Two hedges that do not change the structure:

- Record the fallback demo video (Phase 7) the **first** time the end-to-end path works, not at the end.
- During Phase 2, keep a throwaway script that ingests one TXT file and prints retrieved chunks. It costs nothing and gives Phase 3 a known-good corpus to develop against instead of a moving target.



### Phase 1 — Setup

Monorepo layout, Python venv, `shared/config.py` with every §4.6 limit, OpenRouter wrapper with timeout and retry, `.env` including `ADMIN_TOKEN` and `ALLOWED_INGEST_ROOT`, frontend shell with Pactlify chrome, `/` `/client` `/admin` routes, and mosaic tokens.

Pre-download the embedding model so the first run is not a surprise:

`python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"`

Confirm in a Python REPL that `lancedb.connect(tempfile.mkdtemp())` works, and that a `.where("category = 'pm'")` filter returns what you expect. **Ten minutes here saves hours in Phase 2.**

### Phase 2 — RAG engine

Ingestion (PyMuPDF, pandas, TXT, `urls.txt` with timeout and concurrency cap), optional batch `category` stamp (§4.1), per-type chunking (§4.2), local embeddings off the event loop, LanceDB with build-then-swap, two-level classifier, duplicate suppression, and the public retrieve interface with **prefer-then-backfill** (§4.4). Independent tests (§11) before any agent work.

### Phase 3 — Agent builder (PM + Financial first)

Shared LangGraph state with reducers. Parent router with validated structured output. PM and Financial agents reading `primary_count` for their live-web decision and returning `used_chunk_ids`. Sequential first, then `Send` parallel fan-out and fan-in merge. Then CapEx and General with the same pattern.

`Send` **parallelism is an optimization, not a feature.** Sequential agents produce the identical answer, just slower. If time gets tight, ship sequential — do not let fan-out debugging cost you the CapEx and General agents, which are visible in the demo in a way that concurrency is not.

### Phase 4 — Formatter

Default JSON from §7.3, with deterministic citation derivation and invalid-id dropping per §7.1. Template loader from `resource` / `out` when files appear. Minimal Pactlify PDF from the same envelope (WeasyPrint or ReportLab).

### Phase 5 — API glue

Admin ingest (optional `category`) / documents / override / status behind `Authorization: Bearer ADMIN_TOKEN`, with `ALLOWED_INGEST_ROOT` enforcement. Shared 4xx `{ error, message }` envelope (§8.1). Public `GET /kb` for the header chip. Client query + job status per §7.2 + `GET /report/{job_id}/pdf`. CORS allows the Authorization header. In-memory registry with the active-table pointer and document list. All three timeouts wired. LangSmith env. Single-worker run command documented in the README.

### Phase 6 — Pactlify UI

Implement §3. Mosaic landing. Client two-panel with Answer / Timeline / Sources and Download PDF. Admin pastel category cards, folder-path Submit, document table (id, name, category) backed by `documentStore`. Shared chrome and toggle on every route. Wire `GET /kb` into the header chip.

Generate `types.ts` from the FastAPI OpenAPI schema, or hand-write it once against §7. Do not let the response shape live in two hand-maintained places.

### Phase 7 — Demo prep

Sample folder with 1–2 PDFs, 1 CSV, 1 TXT, `urls.txt`. **Include at least one deliberately mixed document** (budget + timeline in one file) — that is what proves §4.4 works. Pre-cache 2–3 query results. End-to-end: landing → Admin load (auto-detect) → table → Client question → Timeline tab → Answer + Sources → PDF. Fallback video already recorded. Optional LangSmith graph in the demo.

`policy` can be stamped at ingest now. For the default auto-detect path, still exercise **General through** `uncategorized` **documents and ingested** `urls.txt`. A second Submit that stamps Policy is optional, not required.

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
- Ingest with `category="financial"` stamps every file and every `urls.txt` entry `financial`, `overridden = true`, no classifier call.
- Ingest with `category` omitted auto-classifies files; `urls.txt` stays `uncategorized`.

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
- Empty KB → `POST /query` returns `409 kb_empty` and the Client disables Ask. Empty question → `400 empty_query`, no job.
- One agent failure still returns a merged answer from the others; that agent shows `failed` on the timeline.
- An agent exceeding `AGENT_TIMEOUT` is marked failed and does not stall the job.
- A section citing a nonexistent id has that id dropped and a warning added; the job still completes.
- Every `quote` in `citations` is a literal prefix of the corresponding chunk's content.
- `GET /status/{job_id}` with an unknown id returns 404 `{ "error": "job_not_found" }`. A failed job has a non-null top-level `error` and `result: null`.
- `/admin/*` without `Authorization: Bearer` or with the wrong token returns 401 `{ "error": "unauthorized" }`. An ingest path outside `ALLOWED_INGEST_ROOT` returns 403 `{ "error": "forbidden_path" }`.
- Empty / missing folder ingest returns 400 `{ "error": "bad_folder" }` and does not swap the KB.
- `GET /admin/documents` on an empty KB returns `200 { "documents": [] }`.
- `GET /report/{job_id}/pdf` returns `application/pdf` for a completed job with `pdf_available` and 404 `{ "error": "pdf_not_ready" }` otherwise.
- `GET /kb` returns `{ loaded, document_count }` with no path or filenames. After restart it reports `loaded: false`. `GET /kb.loaded` matches `GET /admin/status.loaded`.

---



## 12. Demo script (about 3 minutes)

1. Open `/`. Show the mosaic landing and the four agent tiles. Click **Load documents** or toggle Admin.
2. Enter the token. Leave category cards unselected (auto-detect). Paste the sample folder path, Submit. Show the table: id, name, category, including one `uncategorized`.
3. Toggle Client (or use **Ask the corpus** from landing). Ask a question that needs both PM and Financial.
4. Open **Timeline** while it runs. Switch to **Answer**. Point at a `[c1]` chip → **Sources** highlight. Show a `CROSS` badge if present.
5. Click **Download PDF**.
6. Optional: ask something the corpus barely covers, and show cross-category evidence labelled honestly.
7. If APIs are up, open LangSmith. If they fail, show the pre-cached result.

---



## 13. Key decisions and why


| Decision                          | Why                                                                                                                               |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Two backend modules + one UI      | RAG can be tested alone. Agents only call `retrieve()`. One app, three routes, instead of two frontends.                          |
| Pactlify + mosaic / pastel split  | Landing and Client need an architectural research feel; Admin needs a calm upload surface. One chrome keeps them one product.     |
| Optional category stamp           | Default stays auto-detect. A selected card is an explicit admin override for the whole folder, including `policy` at ingest time. |
| Client tabs + PDF                 | Timeline is inspectable without crowding the answer. PDF is a real demo control, generated from the same envelope.                |
| `documentStore`                   | Admin table must still show id / name / category after toggling away. Server list remains source of truth.                        |
| One HTTP map (§3.7 + §8.1)        | Frontend `api.ts` and FastAPI share field names, status codes, and the Bearer header. No second informal contract.                |
| FastAPI as glue                   | Holds keys, CORS, and the job registry. Not a third domain package.                                                               |
| LanceDB in a temp dir             | Free, no server, no API gamble. Restart behaviour matches the in-memory intent.                                                   |
| Local HuggingFace embeddings      | OpenRouter does not provide embeddings. No extra embedding API key.                                                               |
| Shared folder ingest              | Clients only ask questions. Admin owns the corpus.                                                                                |
| Auto-classify + admin override    | Fast load; admin can mark policy / quick docs. Overrides are disposable in this slice.                                            |
| Chunk-level categories            | A charter's budget table is reachable by Financial even though the file reads as PM.                                              |
| Prefer-then-backfill retrieval    | A misclassification degrades to labelled off-domain evidence instead of a silent "no evidence found."                             |
| Live web keyed on `primary_count` | Preserves "my domain has no docs, go to the web" once backfill exists.                                                            |
| Build-then-swap on reload         | The only way to honour "KB unchanged if the previous load succeeded," and it protects in-flight queries.                          |
| Parent routes agents              | Not every question needs all four agents. Saves time and tokens.                                                                  |
| LangGraph `Send`                  | True parallel fan-out in one superstep. Reducers merge results. Droppable under time pressure.                                    |
| Formatter as a separate layer     | Final envelope applied once. Also the natural place to derive citations, since it sees every agent's chunk ids.                   |
| Citations derived, quotes copied  | The model cannot invent a source or paraphrase a quotation.                                                                       |
| Default JSON now, templates later | Unblocks the Client Answer tab without waiting on the final schema. Minimal PDF uses the same envelope.                           |
| Admin token + ingest root         | The UI toggle is not a security boundary, and ingest reads arbitrary host paths.                                                  |
| Single worker                     | KB and jobs are in-process; multiple workers cause intermittent empty-KB reads.                                                   |


---



## 14. Gotchas


| Risk                                                            | Mitigation                                                                                |
| --------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Hard category filter silently loses evidence                    | Prefer-then-backfill with `cross_category` flags (§4.4).                                  |
| Classifier forced into a wrong bucket                           | `uncategorized` is a legal classifier output.                                             |
| `lancedb.EphemeralClient()` does not exist                      | ChromaDB API from the v1.0 docx. Use `lancedb.connect(tempfile.mkdtemp())`.               |
| LanceDB filters are SQL strings, not dicts                      | One quoting helper in `vectorstore.py`. Never interpolate raw filenames.                  |
| NULL category matches nothing in SQL                            | Store the literal `'uncategorized'`. Never NULL.                                          |
| Multiple uvicorn workers → intermittent empty KB                | `--workers 1`, no `--reload`.                                                             |
| Embedding blocks the event loop                                 | `await asyncio.to_thread(...)` around every embed and search.                             |
| Reload during a live query corrupts it                          | Build-then-swap; jobs hold their table handle (§4.3).                                     |
| Reload appends instead of replaces                              | New table per ingest, never `add()` onto the live one.                                    |
| Parallel agents overwrite shared state                          | `Annotated[list, operator.add]` on fields agents write.                                   |
| Unbounded LLM or web calls hang the demo                        | `LLM_TIMEOUT`, `AGENT_TIMEOUT`, `JOB_TIMEOUT` (§4.6).                                     |
| One slow URL stalls the whole folder load                       | `URL_FETCH_TIMEOUT` + `URL_FETCH_CONCURRENCY`.                                            |
| Model invents citation ids or paraphrases quotes                | Formatter derives ids from real chunks; `quote` is copied text (§7.1).                    |
| CSV chunks split mid-row and lose the header                    | Row-bounded chunking, header repeated, `row_start` / `row_end` (§4.2).                    |
| Boilerplate crowds out real evidence in `TOP_K`                 | Content-hash duplicate suppression at ingest.                                             |
| Router names an agent that is not built yet                     | Validate against built agents; fall through to the §9 fallback.                           |
| Admin endpoints are unauthenticated                             | `ADMIN_TOKEN` + `ALLOWED_INGEST_ROOT`.                                                    |
| No end-to-end path until Phase 5                                | Accepted. Record the fallback video at first success; keep a Phase 2 smoke script.        |
| In-memory KB and jobs die on restart                            | Accepted. Admin reloads the folder. Client gets a 404 and asks again.                     |
| Overrides die on reload, so `policy` is empty unless re-stamped | Accepted. Demo General through `uncategorized` + web, or stamp Policy on a second Submit. |
| Two visual systems drift into one muddy theme                   | Mosaic tokens only on landing/Client/header. Pastel tokens only on Admin body.            |
| Admin table empty after toggle                                  | Hydrate from `GET /admin/documents`; keep `documentStore` for the session.                |
| Large CSVs create too many chunks                               | Batch 10–50 rows per document.                                                            |
| API keys in the frontend                                        | Keys stay in FastAPI `.env` only.                                                         |
| Slow or down live APIs during demo                              | Pre-cache 2–3 results. Warnings on the job, do not block.                                 |
| LangSmith shows nothing                                         | Set `LANGCHAIN_TRACING_V2` and `LANGCHAIN_API_KEY` before start. Tracing is optional.     |
| WeasyPrint system deps                                          | ReportLab fallback so **Download PDF** still works in the demo.                           |
| First embedding-model download is slow                          | Pre-download during setup.                                                                |
| ChromaDB leftover from the v1.0 docx                            | Do not use ChromaDB. LanceDB only.                                                        |
| Flaky retrieval tests                                           | Deterministic fake embedder for unit tests.                                               |


---



## 15. Deferred (explicit, not missing)

- Final JSON schema and branded PDF layout (files under `resource` / `out`). The first-slice PDF is intentionally plain.
- Browser file-drop as a real ingest path (this slice is server folder path only).
- Row-level retag UI on the Admin table (`PATCH` exists; the first-slice table is read-only).
- Real login and role-based Admin vs Client (replaces the toggle; `ADMIN_TOKEN` is the interim guard).
- Durable LanceDB.
- Saved classification overrides, and the optional `categories.txt` folder manifest that would make `policy` reproducible across reloads.
- True RAM-resident LanceDB via a `memory://` connection, if it verifies on the installed version.
- Chunk-level classification by LLM rather than heuristic, if the heuristic proves too coarse.
- Client query history.
- Finance-lead persona polish (PM + Financial behavior is enough for the first slice).

---



## 16. What you will still provide during implementation

- Sample documents in one folder (1–2 PDFs, 1 CSV, 1 TXT, optional `urls.txt`) for PM and financial questions, **including one deliberately mixed document** so §4.4 is demonstrable.
- Agent prompt details if Financial / PM / CapEx / General need a specific analysis framework.
- Final JSON and PDF templates when ready; drop them into `resource` / `out` without changing agent internals.
- Optional wordmark / logo asset; until then the header is the text **Pactlify**.

