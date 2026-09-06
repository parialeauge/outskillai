# Pactlify Frontend Implementation Plan (v5.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Pactlify UI: one React + TypeScript app with four routes (`/`, `/app`, `/client`, `/admin`), constellation marketing `/`, mosaic hub `/app` + Client, pastel Admin body, mosaic chrome on workspace routes, and an `api.ts` that talks the v4.0 wire contract — first against fixtures, then against the live FastAPI.

**Architecture:** Look-and-feel is in scope. The Client is built against mocked §7.2 / §7.3 envelopes before the API exists. `api.ts` is the only HTTP client; every UI action maps to exactly one §3.7 call. Phase 6 changes the body of those functions from fixtures to `fetch` and nothing else. Keep fixtures afterward as test data. Keys never live in the frontend.

**Tech Stack:** React + TypeScript, Vite, React Router, CSS modules or plain CSS (`theme/constellation.css`, `theme/mosaic.css`, `theme/pastel.css`). Fonts: Space Grotesk (display/UI), Inter (constellation subhead), JetBrains Mono (labels, ids, status, citation chips). No component library required.

**Source of truth:** `outskillai/planning/Updated-Architecture-and-Build-Plan-v4.0_Opus5.md`. This file is the frontend-only implementation plan derived from it.

**Companion:** Backend plan is `outskillai/planning/Updated-Architecture-and-Build-Plan-v4.0_Opus5-app.md`. Do not implement Python, LanceDB, or agents here. Prefer backend-generated JSON in `frontend/src/fixtures/` when those files exist; until then hand-write fixtures that match the envelopes in this plan exactly.

## Global Constraints

- Product name: **Pactlify.** Wordmark **Pactlify** returns to `/`.
- One React + TypeScript app. Routes: `/` constellation, `/app` mosaic hub, `/client`, `/admin`.
- Mosaic chrome on `/app`, `/client`, `/admin`: **Pactlify** + **Admin | Client** toggle + KB/job chip. Hidden on `/`.
- Visual systems: `/` = [Constellation Network](https://superdesign.dev/library?category=animation&selected=animated-hero-section-constellation-network-landing-page) (canvas `#f4f6f2`, ink `#111111`, lime `#a3e635`). `/app` + Client + **header on workspace pages** = Mosaic Grid Architecture (forest `#1A3C2B`, paper `#F7F7F5`, Space Grotesk + JetBrains Mono, bento, 1px hairlines, **zero shadows**). Admin **body only** = Promptly pastel card-grid (peach canvas, white rounded cards, colored dots, soft shadow on cards). Do not mix.
- Toggle is UI convenience, **not** a security boundary. Admin API calls still send `Authorization: Bearer <ADMIN_TOKEN>`. Token prompted once, held in memory for the tab session, never sent on `/kb`, `/query`, `/status/`*, or `/report/`*.
- Clients never upload. No source picker. No per-user history. Submitted question text stays in the field.
- Base URL: `VITE_API_BASE_URL` (default `http://localhost:8000`). JSON `Content-Type: application/json` except PDF download.
- Shared 4xx body: `{ "error": "error_code", "message": "human-readable string" }`.
- Status vocabulary is **only** the seven-state enum: `queued` | `routing` | `running` | `merging` | `formatting` | `completed` | `failed`. The UI must have a label for every member.
- Agent timeline status: `pending` | `retrieving` | `searching_web` | `synthesizing` | `done` | `failed`.
- Ingest is synchronous. Admin Submit spinner. Frontend ingest timeout is **300s**. Until the response returns, `GET /kb` still shows the previous KB.
- Auto-detect / no card selected: **omit** `category` from the ingest body. Do **not** send `"uncategorized"`.
- Download PDF enabled only when `status === "completed"` **and** `result.pdf_available === true`. Filename `pactlify-{job_id}.pdf`.
- Admin table maps wire fields only: `id` ← `document_id`, `name` ← `source`, `category` ← `category`. Do not rename fields on the wire.
- First-slice Admin table is **read-only**. Do not call `PATCH /admin/documents/{id}`.
- Banner above Client tabs reads **only** top-level §7.2 `warnings[]`. Do not merge or de-duplicate with `result.warnings[]`.
- `GET /kb` failure → chrome chip shows `KB empty`. Never display folder path or filenames from `/kb` (the payload has neither).
- Empty KB Client copy: *Knowledge base not loaded — ask admin.* 409 `kb_empty` uses the same sentence.
- Job 404 copy: *Job no longer available — please ask again.*
- No API keys in the frontend.

---



## Out of scope (this plan)

- `rag_engine`, `agent_builder`, FastAPI, LanceDB, ingest internals, agent prompts — backend plan.
- Browser file-drop as a real ingest path (server folder path only).
- Row-level retag UI (PATCH exists on the backend; table stays read-only).
- Real login / roles (toggle stays until a later slice).
- Client query history.
- Custom branded PDF layout (the UI only downloads whatever `/report/{id}/pdf` returns).
- Calling `clear()` or inventing extra HTTP endpoints.

---



## File map

```
outskillai/frontend/
├── package.json
├── vite.config.ts
├── index.html
├── tsconfig.json
├── .env.example                      # VITE_API_BASE_URL=http://localhost:8000
└── src/
    ├── main.tsx
    ├── App.tsx                       # chrome + routes
    ├── api.ts                        # the only HTTP client
    ├── types.ts                      # mirrors §7 + §7.2 + DocumentInfo
    ├── pages/ConstellationLanding.tsx
    ├── pages/Landing.tsx
    ├── pages/Client.tsx
    ├── pages/Admin.tsx
    ├── components/Chrome.tsx
    ├── components/KbChip.tsx
    ├── components/AnswerTab.tsx
    ├── components/TimelineTab.tsx
    ├── components/SourcesTab.tsx
    ├── components/CategoryCards.tsx
    ├── components/DocumentTable.tsx
    ├── stores/documentStore.ts
    ├── stores/tokenStore.ts          # ADMIN_TOKEN in memory
    ├── stores/jobChipStore.ts        # "Job running" text for the chrome chip
    ├── fixtures/
    │   ├── kb-empty.json
    │   ├── kb-loaded.json
    │   ├── admin-status-empty.json
    │   ├── admin-status-loaded.json
    │   ├── admin-documents.json
    │   ├── ingest-success.json
    │   ├── job-queued.json
    │   ├── job-routing.json
    │   ├── job-running.json
    │   ├── job-merging.json
    │   ├── job-formatting.json
    │   ├── job-completed-multi.json
    │   ├── job-cross.json
    │   ├── job-agent-failed.json
    │   ├── job-dropped-citation.json
    │   └── job-failed.json
    └── theme/
        ├── constellation.css
        ├── mosaic.css
        └── pastel.css
```

---



## Wire contract this plan must consume

Every UI action calls exactly one of these. No other HTTP endpoints exist in this slice.

Admin auth header (every `/admin/*` call):

```
Authorization: Bearer <ADMIN_TOKEN>
```


| UI surface                   | When                                                   | Call                                            | Success                                                                                              | UI on failure                                                                    |
| ---------------------------- | ------------------------------------------------------ | ----------------------------------------------- | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Chrome + `/app` status tile | Mount, after ingest success, every ~5s                 | `GET /kb`                                       | `{ loaded, document_count }`                                                                         | Chip shows `KB empty` if the call fails                                          |
| Admin first visit            | Before any `/admin/*`                                  | none (local prompt)                             | token in memory                                                                                      | —                                                                                |
| Admin mount                  | After token                                            | `GET /admin/status` then `GET /admin/documents` | hydrate path field, failures, table                                                                  | `401` → re-prompt token; empty list → *No documents loaded.*                     |
| Admin Submit                 | Click Submit                                           | `POST /admin/ingest`                            | replace `documentStore` + table from `documents`; show `failed_*` under the table; refresh `GET /kb` | `401` re-prompt; `403` path rejected; `400` folder error; previous table/KB stay |
| Admin table columns          | Render                                                 | map only                                        | `id` ← `document_id`; `name` ← `source`; `category` ← `category`                                     | —                                                                                |
| Client Ask enable            | Mount + `GET /kb`                                      | `GET /kb`                                       | Ask enabled iff `loaded === true`                                                                    | Ask stays disabled                                                               |
| Client Ask                   | Click Ask                                              | `POST /query`                                   | start polling `job_id`                                                                               | `400 empty_query` inline; `409 kb_empty` disable Ask                             |
| Client tabs                  | After Ask, every ~1s                                   | `GET /status/{job_id}`                          | render status, timeline, result                                                                      | `404` → *Job no longer available — please ask again.*                            |
| Download PDF                 | Answer tab, job `completed` and `result.pdf_available` | `GET /report/{job_id}/pdf`                      | save blob as `pactlify-{job_id}.pdf`                                                                 | stay disabled; do not invent a PDF                                               |


`documentStore` holds: `documents: DocumentInfo[]`, `failed_files`, `failed_urls`, `last_folder`. Replaced on successful ingest. Cleared if `GET /admin/documents` returns an empty `documents` array after a restart.

---



## Types (lock these names)

Hand-write `types.ts` against this block now. After the backend ships OpenAPI, regenerate and delete the hand-written duplicate — the response shape must not live in two maintained places.

```typescript
export type Category = "financial" | "pm" | "capex" | "policy" | "uncategorized";
export type StampCategory = "financial" | "pm" | "capex" | "policy"; // never "uncategorized"
export type DocType = "pdf" | "csv" | "txt" | "web";

export type JobStatus =
  | "queued"
  | "routing"
  | "running"
  | "merging"
  | "formatting"
  | "completed"
  | "failed";

export type AgentName = "financial" | "pm" | "capex" | "general";

export type AgentRunStatus =
  | "pending"
  | "retrieving"
  | "searching_web"
  | "synthesizing"
  | "done"
  | "failed";

export interface ApiErrorBody {
  error: string;
  message: string;
}

export interface KbInfo {
  loaded: boolean;
  document_count: number;
}

export interface FailedFile {
  name: string;
  reason: string;
}

export interface FailedUrl {
  url: string;
  reason: string;
}

export interface DocumentInfo {
  document_id: string;
  source: string;
  type: DocType;
  chunk_count: number;
  auto_category: Category;
  category: Category;
  overridden: boolean;
}

export interface AdminStatus {
  loaded: boolean;
  last_folder: string | null;
  document_count: number;
  chunk_count: number;
  failed_files: FailedFile[];
  failed_urls: FailedUrl[];
}

export interface IngestRequest {
  folder_path: string;
  category?: StampCategory | null;
}

export interface IngestResult {
  knowledge_base_id: "shared";
  documents: DocumentInfo[];
  failed_files: FailedFile[];
  failed_urls: FailedUrl[];
  chunk_count: number;
}

export interface TimelineEntry {
  agent: AgentName;
  status: AgentRunStatus;
  started_at: string;
  finished_at: string | null;
  chunks_retrieved: number;
  primary_count: number;
  used_live_web: boolean;
  error: string | null;
}

export interface Citation {
  id: string;
  source: string;
  type: DocType;
  category: Category;
  page: number | null;
  row_start: number | null;
  row_end: number | null;
  cross_category: boolean;
  quote: string;
}

export interface AnswerSection {
  agent: AgentName;
  title: string;
  body: string;
  key_points: string[];
  citation_ids: string[];
}

export interface JobResult {
  job_id: string;
  query: string;
  activated_agents: AgentName[];
  answer: {
    summary: string;
    sections: AnswerSection[];
  };
  citations: Citation[];
  warnings: string[];
  pdf_available: boolean;
}

export interface JobStatusPayload {
  job_id: string;
  status: JobStatus;
  query: string;
  created_at: string;
  activated_agents: AgentName[];
  timeline: TimelineEntry[];
  warnings: string[];
  error: string | null;
  result: JobResult | null;
}
```

Job-status labels (every enum member):


| `status`     | Label (JetBrains Mono) |
| ------------ | ---------------------- |
| `queued`     | `QUEUED`               |
| `routing`    | `ROUTING`              |
| `running`    | `RUNNING`              |
| `merging`    | `MERGING`              |
| `formatting` | `FORMATTING`           |
| `completed`  | `COMPLETED`            |
| `failed`     | `FAILED`               |


---



### Task 1: Vite + TypeScript shell and mosaic tokens

**Files:**

- Create: `outskillai/frontend/package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/main.tsx`
- Create: `outskillai/frontend/src/theme/mosaic.css`
- Create: `outskillai/frontend/.env.example`

**Interfaces:**

- Consumes: nothing
- Produces: a running app at `/` that loads Space Grotesk + JetBrains Mono and paints paper `#F7F7F5` / forest `#1A3C2B`

- [ ] **Step 1: Scaffold Vite React-TS in** `outskillai/frontend/`**.** App title `Pactlify`. `VITE_API_BASE_URL` defaults to `http://localhost:8000`.
- [ ] **Step 2: Write** `mosaic.css` **tokens**

```css
:root {
  --paper: #F7F7F5;
  --forest: #1A3C2B;
  --ink: #1A3C2B;
  --hairline: 1px solid var(--forest);
  --font-display: "Space Grotesk", sans-serif;
  --font-mono: "JetBrains Mono", monospace;
}

html, body, #root {
  background: var(--paper);
  color: var(--ink);
  font-family: var(--font-display);
  box-shadow: none;
}

.btn-primary {
  background: var(--forest);
  color: var(--paper);
  border: var(--hairline);
  box-shadow: none;
}
```

Load fonts from a public source (Google Fonts or self-host). **Zero shadows** on mosaic surfaces.

- [ ] **Step 3: Run** `npm install` **and** `npm run dev`**.** Expected: blank paper page, no console errors.

- [ ] **Step 4: Commit** `chore: scaffold Pactlify Vite app with mosaic tokens`

---



### Task 2: `types.ts`

**Files:**

- Create: `outskillai/frontend/src/types.ts`
- Test: `outskillai/frontend/src/types.test.ts` if a test runner exists; otherwise a `tsc --noEmit` check is the gate

**Interfaces:**

- Consumes: the Types section above
- Produces: exported types used by every later file. Do not invent parallel names (`id` vs `document_id` belongs in the table mapper, not in `DocumentInfo`).

- [ ] **Step 1: Paste the Types block into** `types.ts` **as written.**
- [ ] **Step 2:** `npx tsc --noEmit` **— expect PASS.**
- [ ] **Step 3: Commit** `feat: lock Pactlify API types against the v4.0 envelope`

---



### Task 3: Fixtures for every Client and Admin state

**Files:**

- Create: every JSON file under `outskillai/frontend/src/fixtures/` listed in the file map

**Interfaces:**

- Consumes: `types.ts`
- Produces: deterministic payloads covering: empty KB, populated KB, multi-agent completed job, `CROSS` citation, one `failed` agent beside successful ones, dropped-citation warning, fully `failed` job, all seven job statuses, populated document table

If `frontend/src/fixtures/job-*.json` already exist from the backend formatter, **use those** and only hand-write the ones still missing.

- [ ] **Step 1: Write** `kb-empty.json`

```json
{ "loaded": false, "document_count": 0 }
```

- [ ] **Step 2: Write** `kb-loaded.json`

```json
{ "loaded": true, "document_count": 4 }
```

- [ ] **Step 3: Write** `admin-documents.json` with at least four `DocumentInfo` rows including one `uncategorized` and one `overridden: true`. Required columns must be present: `document_id`, `source`, `category`.

- [ ] **Step 4: Write** `job-completed-multi.json` as a full `JobStatusPayload` with `status: "completed"`, `activated_agents: ["financial", "pm"]`, non-null `result`, `result.pdf_available: true`, at least one citation id used in a section.

- [ ] **Step 5: Write** `job-cross.json` with a citation `{ "cross_category": true }` and a section that references it.

- [ ] **Step 6: Write** `job-agent-failed.json` with one timeline row `status: "failed"` and another `status: "done"`, overall `status: "completed"`, non-null `result`.

- [ ] **Step 7: Write** `job-dropped-citation.json` with a top-level `warnings` entry about a dropped citation id, `status: "completed"`.

- [ ] **Step 8: Write** `job-failed.json` with `status: "failed"`, non-null `error`, `result: null`.

- [ ] **Step 9: Write one fixture per remaining status** (`queued`, `routing`, `running`, `merging`, `formatting`) so the status label can be screenshot independently. `result` is `null` on all of these.

- [ ] **Step 10: Write empty and loaded** `admin-status-*.json` **plus** `ingest-success.json` matching `AdminStatus` / `IngestResult`.

- [ ] **Step 11: Commit** `test: add Pactlify UI fixtures for every job and admin state`

---



### Task 4: `api.ts` fixture adapter

**Files:**

- Create: `outskillai/frontend/src/api.ts`
- Create: `outskillai/frontend/src/stores/tokenStore.ts`

**Interfaces:**

- Consumes: fixtures, `types.ts`, `VITE_API_BASE_URL`
- Produces: these exact function names (Phase 6 changes bodies only):

```typescript
export function setAdminToken(token: string | null): void;
export function getAdminToken(): string | null;

export function getKb(): Promise<KbInfo>;
export function getAdminStatus(): Promise<AdminStatus>;
export function getAdminDocuments(): Promise<{ documents: DocumentInfo[] }>;
export function ingest(body: IngestRequest): Promise<IngestResult>;
export function postQuery(query: string): Promise<{ job_id: string }>;
export function getStatus(jobId: string): Promise<JobStatusPayload>;
export function getReportPdf(jobId: string): Promise<Blob>;
```

Throw a typed error `{ status: number, body: ApiErrorBody }` on 4xx. Fixture mode:

- `getKb` returns `kb-empty.json` until a successful fixture ingest, then `kb-loaded.json`.
- `ingest` with folder path `__empty__` throws `{ status: 400, body: { error: "bad_folder", message: "Folder is empty or missing — scan is top-level files only." } }`; with `__forbidden__` throws `{ status: 403, body: { error: "forbidden_path", message: "Path is outside ALLOWED_INGEST_ROOT." } }`; with `__unauth__` throws `{ status: 401, body: { error: "unauthorized", message: "Missing or wrong admin token." } }`; otherwise returns `ingest-success.json`.
- `postQuery` with `""` (caller should not send this) throws 400 `empty_query`; if kb not loaded throws 409 `kb_empty` with message `Knowledge base not loaded — ask admin.`; otherwise returns `{ job_id: "job_fixture" }`.
- `getStatus("job_fixture")` can cycle queued → … → completed-multi, or accept a query-param / localStorage `PACTLIFY_FIXTURE` override (`cross`, `agent-failed`, `dropped`, `failed`, `gone`) so every state is clickable. `getStatus` unknown id throws 404 `job_not_found`.
- `getReportPdf` returns a tiny valid PDF `Blob` when the completed fixture has `pdf_available: true`; otherwise throws 404 `pdf_not_ready`.

`tokenStore` holds the bearer string in a module variable (memory only). Fixture `getAdminStatus` / `getAdminDocuments` / `ingest` throw 401 if token is null.

- [ ] **Step 1: Implement** `tokenStore.ts` **and** `api.ts` **in fixture mode.** Do not call `fetch` yet.

- [ ] **Step 2: Manual check:** `getKb()` → `loaded: false`; after `ingest({ folder_path: "/allowed/sample_data" })` → `getKb().loaded === true`.

- [ ] **Step 3: Commit** `feat: add api.ts fixture client with the locked function signatures`

---



### Task 5: `documentStore`

**Files:**

- Create: `outskillai/frontend/src/stores/documentStore.ts`

**Interfaces:**

- Consumes: `DocumentInfo`, `FailedFile`, `FailedUrl`
- Produces:

```typescript
export interface DocumentStoreState {
  documents: DocumentInfo[];
  failed_files: FailedFile[];
  failed_urls: FailedUrl[];
  last_folder: string | null;
}

export function getDocumentStore(): DocumentStoreState;
export function replaceFromIngest(result: IngestResult, folder: string): void;
export function hydrateFromAdmin(docs: DocumentInfo[], status: AdminStatus): void;
export function clearIfServerEmpty(docs: DocumentInfo[]): void; // empty array → reset store
```

Subscribe via a tiny listener set or React state lifted in `Admin.tsx`. Server list is source of truth; the store only prevents an empty flash when toggling away and back.

- [ ] **Step 1: Implement the store.** `clearIfServerEmpty([])` resets to empty arrays and `last_folder: null`.

- [ ] **Step 2: Commit** `feat: keep a session copy of the admin document list`

---



### Task 6: Shared chrome and routes

**Files:**

- Create: `outskillai/frontend/src/App.tsx`
- Create: `outskillai/frontend/src/components/Chrome.tsx`
- Create: `outskillai/frontend/src/components/KbChip.tsx`
- Create: `outskillai/frontend/src/stores/jobChipStore.ts`
- Modify: `outskillai/frontend/src/main.tsx` to wrap `BrowserRouter`

**Interfaces:**

- Consumes: `getKb()`, React Router
- Produces: chrome on `/app`, `/client`, `/admin`. Hidden on `/`.

Chrome slots:

- Left: wordmark **Pactlify** → `/`
- Center-right: segmented toggle **Admin | Client** navigating to `/admin` or `/client`
- Far right: chip `KB empty` / `KB loaded · N docs` / `Job running`. KB counts from `GET /kb` on mount, after ingest success, and every ~5s. Job text from `jobChipStore`: Client polling (Task 9) calls `setJobChip("Job running")` while status is one of `queued|routing|running|merging|formatting`, and `setJobChip(null)` on `completed`, `failed`, or 404 so the chip falls back to KB state.

```typescript
// stores/jobChipStore.ts
let jobLabel: string | null = null;
const listeners = new Set<() => void>();
export function setJobChip(label: string | null): void {
  jobLabel = label;
  listeners.forEach((l) => l());
}
export function getJobChip(): string | null {
  return jobLabel;
}
export function subscribeJobChip(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
```

`KbChip` prefers `getJobChip()` when non-null; otherwise it renders `KB empty` or `KB loaded · ${n} docs`. Chip on `getKb` failure: `KB empty`.

Placeholder page components are allowed in this task (`<h1>Landing</h1>` etc.) so routing works before Tasks 7–11.

- [ ] **Step 1: Implement** `Chrome` **+ routes.** Toggle is not auth.

- [ ] **Step 2: Verify in the browser:** wordmark returns to `/`; toggle moves between `/admin` and `/client`; chip shows `KB empty` against the empty fixture; `/` has no mosaic chrome.

- [ ] **Step 3: Commit** `feat: add Pactlify chrome, routes, and KB chip`

---



### Task 7: Constellation marketing `/` and mosaic hub `/app`

**Files:**

- Create: `outskillai/frontend/src/pages/ConstellationLanding.tsx`
- Create: `outskillai/frontend/src/theme/constellation.css`
- Create: `outskillai/frontend/src/pages/Landing.tsx`

**Interfaces:**

- Consumes: chrome (on `/app` only), `getKb()` for the mosaic status tile
- Produces: constellation hero at `/`; mosaic hero + bento at `/app`. Neither page starts a job. `/` does not call `GET /kb`.

**`/` — Constellation Network hero** ([library prompt](https://superdesign.dev/library?category=animation&selected=animated-hero-section-constellation-network-landing-page)):

1. Pale canvas `#f4f6f2`, ink `#111111`, lime `#a3e635`
2. Full-bleed SVG node-network with CSS drift; one cluster glows lime
3. Eyebrow `MULTI-AGENT RESEARCH`, headline *Ask the Corpus.* — *Ask the* at 64% of the headline size, lime sweep on **Corpus**
4. **Start building** → `/app` (opens the mosaic hub)
5. Ghost **Load documents** → `/admin`
6. Trust row: Financial · PM · CapEx · General · Cited PDF
7. Pipeline strip: **Client** → **UI Interface** → **Multi-Agent Worker** → **Tools** → **RAG Engine** → **Response and Report**
8. `prefers-reduced-motion` disables drift/pulse/sweep

**`/app` — mosaic hub** (previous landing):

1. Hero band: mono label `MULTI-AGENT RESEARCH`, headline, one-line pitch: *Pactlify — ask the corpus; specialists cite what they used.*
2. Tiles:
  - Large **Ask the corpus** → `/client`
  - **Load documents** → `/admin`
  - Four **non-link** agent tiles: Financial, PM, CapEx, General
  - Status tile repeating KB state (`KB empty` or `KB loaded · N docs`)
3. Footer strip: admin loads a folder; clients only ask. No upload here.

Empty KB is allowed on `/app`.

- [ ] **Step 1: Implement** `ConstellationLanding.tsx` **and** `Landing.tsx` **(mosaic hairlines, no shadows, bento grid).**

- [ ] **Step 2: Browser check:** `/` has no chrome; **Start building** opens `/app`; both mosaic CTAs navigate; agent tiles do not navigate; empty KB still renders.

- [ ] **Step 3: Commit** `feat: add constellation marketing hero and move mosaic hub to /app`

---



### Task 8: Client left pane (search)

**Files:**

- Create: `outskillai/frontend/src/pages/Client.tsx` (left pane first; right pane placeholder)

**Interfaces:**

- Consumes: `getKb()`, `postQuery()`
- Produces: mosaic two-panel; left ~36% search only

Left pane:

- Mono label `QUERY`
- Multi-line question field
- **Ask** forest primary
- Helper: `Parent routes to Financial, PM, CapEx, General.`
- Empty KB: Ask **disabled**; copy *Knowledge base not loaded — ask admin.*
- Empty question: reject, no `postQuery`
- Submitted text **stays** in the field (no history list)
- No upload, no source picker, no category cards

On Ask: trim; if empty, inline error and no job; if 409 `kb_empty`, disable Ask and show that message; if 400 `empty_query`, inline error; on `{ job_id }`, begin polling (Task 9).

- [ ] **Step 1: Implement left pane against fixtures (Ask disabled on empty KB).**

- [ ] **Step 2: Temporarily point fixture KB to loaded, type a question, click Ask, confirm** `postQuery` **is called once and the text remains.**

- [ ] **Step 3: Commit** `feat: add Client query pane with empty-KB and empty-question guards`

---



### Task 9: Client right pane shell — status, tabs, banner

**Files:**

- Modify: `outskillai/frontend/src/pages/Client.tsx`
- Create: `outskillai/frontend/src/components/AnswerTab.tsx` (stub)
- Create: `outskillai/frontend/src/components/TimelineTab.tsx` (stub)
- Create: `outskillai/frontend/src/components/SourcesTab.tsx` (stub)

**Interfaces:**

- Consumes: `getStatus(jobId)` every ~1s after Ask
- Produces: right pane ~64% with mono job status **above** tabs **Answer | Timeline | Sources**, and a slim warnings banner above the tabs reading `payload.warnings` only

Poll until `completed` or `failed` or 404. User may open Timeline while the job runs. Status label uses the seven-state table. `404` → *Job no longer available — please ask again.* Stop polling on 404.

Call `setJobChip("Job running")` when polling starts and while status is `queued`, `routing`, `running`, `merging`, or `formatting`. Call `setJobChip(null)` when the job completes, fails, 404s, or the user leaves `/client`.

- [ ] **Step 1: Implement polling and the seven labels.** Cycle the fixture through queued → completed and confirm each label appears.

- [ ] **Step 2: Render** `job-dropped-citation.json` **warnings as a banner. Do not read** `result.warnings` **for the banner.**

- [ ] **Step 3: Commit** `feat: poll job status and tab the Client result pane`

---



### Task 10: Answer tab, CROSS badge, Download PDF

**Files:**

- Modify: `outskillai/frontend/src/components/AnswerTab.tsx`
- Modify: `outskillai/frontend/src/pages/Client.tsx`

**Interfaces:**

- Consumes: `JobResult`, `getReportPdf(jobId)`
- Produces: summary, then one block per activated agent (title, body, key points, citation chips `[c1]`). Cross-category citations get a hairline `CROSS` badge. **Download PDF** top-right of this tab.

PDF button:

- Visible always on the Answer tab
- Enabled only when `status === "completed"` **and** `result.pdf_available === true`
- Click → `GET /report/{job_id}/pdf` as blob download named `pactlify-{job_id}.pdf`
- On failure: stay disabled / show no fake PDF
- Job `failed`: short reason, no fabricated answer, PDF stays disabled

Citation chip click is wired in Task 11 (switch to Sources + highlight). In this task, chips may be inert or call a `onCiteClick(id)` prop already.

- [ ] **Step 1: Render** `job-completed-multi.json` **and** `job-cross.json`**. Confirm** `CROSS` **on the backfilled citation.**

- [ ] **Step 2: Enable Download against the completed fixture; confirm a file named** `pactlify-job_fixture.pdf` **saves. Confirm it stays disabled on** `job-failed.json`**.**

- [ ] **Step 3: Commit** `feat: render the Answer tab with CROSS badges and PDF download`

---



### Task 11: Timeline and Sources tabs

**Files:**

- Modify: `outskillai/frontend/src/components/TimelineTab.tsx`
- Modify: `outskillai/frontend/src/components/SourcesTab.tsx`
- Modify: `outskillai/frontend/src/pages/Client.tsx`

**Interfaces:**

- Consumes: `timeline[]`, `result.citations`, selected citation id from Answer chips
- Produces: Timeline rows and Sources rows

Timeline: one row per activated agent: name, status (`pending | retrieving | searching_web | synthesizing | done | failed`), `chunks_retrieved`, `primary_count`, `used_live_web`, error. One failed agent does not hide the others (`job-agent-failed.json`).

Sources: id, source, type, category, page or `row_start`/`row_end`, verbatim `quote`, `CROSS` if `cross_category`. Clicking an Answer chip switches to Sources and highlights that row.

- [ ] **Step 1: Implement Timeline against** `job-agent-failed.json` **and a running fixture.**

- [ ] **Step 2: Implement Sources + chip → highlight.**

- [ ] **Step 3: Browser check all five job fixtures (multi, cross, agent-failed, dropped-citation, failed) plus empty KB.**

- [ ] **Step 4: Commit** `feat: add Timeline and Sources tabs with citation highlight`

---



### Task 12: Pastel Admin — token, cards, folder submit

**Files:**

- Create: `outskillai/frontend/src/theme/pastel.css`
- Create: `outskillai/frontend/src/pages/Admin.tsx`
- Create: `outskillai/frontend/src/components/CategoryCards.tsx`

**Interfaces:**

- Consumes: `setAdminToken`, `getAdminStatus`, `ingest`, mosaic header (already in chrome)
- Produces: Admin body on peach canvas. Admin does **not** run research questions.

`pastel.css` (Admin body only, not the header):

- Pale peach / off-white canvas
- White cards, ~20px radius, thin light border, **soft shadow allowed here**
- Bold dark title, gray description, colored dot top-right
- Selected card: thicker tinted border (no second “selected” language on the card)

First visit: prompt once for `ADMIN_TOKEN`, hold in memory. `401` stays on the page and re-prompts.

Category cards: 3-column grid, five cards (last row holds two). Cards do not list files. Optional **single-select**.


| Card                   | Dot      | Stamp                                             |
| ---------------------- | -------- | ------------------------------------------------- |
| Financial              | coral    | `financial`                                       |
| Project Manager        | sky      | `pm`                                              |
| CapEx                  | mint     | `capex`                                           |
| Policy                 | lavender | `policy`                                          |
| Auto-detect / unmarked | gray     | none (default visual; equivalent to no selection) |


- Click a card to select; click again to clear.
- Nothing selected = auto-detect = **omit** `category` on ingest.
- One card selected = send that stamp. Never send `"uncategorized"`.

Upload panel (below, full width):

- Folder path field. Contract is `{ "folder_path": "...", "category": <optional> }`. No browser file-drop as a substitute.
- Submit → `POST /admin/ingest` with 300s timeout and a spinner. Reload **replaces** the table from the response.
- Visible note: table and stamps are in-memory; restart requires the path again.
- Errors: 401 re-prompt; 403 path rejected (message); 400 folder error (message); previous table stays on failure.

- [ ] **Step 1: Implement token prompt + cards + path field + Submit against fixtures.** Default visual is Auto-detect selected-or-none equivalent.
- [ ] **Step 2: Browser check:** omit `category` when nothing / auto-detect; send `pm` when Project Manager is selected; `__forbidden__` shows a path error and does not wipe a previously loaded table.
- [ ] **Step 3: Commit** `feat: add pastel Admin category stamp and folder ingest`

---



### Task 13: Admin document table and failure lists

**Files:**

- Create: `outskillai/frontend/src/components/DocumentTable.tsx`
- Modify: `outskillai/frontend/src/pages/Admin.tsx`

**Interfaces:**

- Consumes: `getAdminStatus`, `getAdminDocuments`, `documentStore`, ingest response
- Produces: table columns **id**, **name**, **category** (effective). Optional extras: type, chunk count, auto vs overridden.

Hydrate on mount from `GET /admin/status` then `GET /admin/documents`. After Submit, use the ingest response; do not require a second list call (a refresh of both is still allowed). Empty: *No documents loaded.* `failed_files` / `failed_urls` render as a short error list **under** the table, never as success rows. Table is read-only.

On mount, if documents array is empty, `clearIfServerEmpty` so a restart does not keep the previous session table.

- [ ] **Step 1: Implement table mapping** `document_id` **→ id,** `source` **→ name,** `category` **→ category.**

- [ ] **Step 2: Browser check:** toggle to Client and back — table does not flash empty if store has rows; empty fixture shows *No documents loaded.*; failures list under the table.

- [ ] **Step 3: Commit** `feat: fill the Admin document table from ingest and documentStore`

---



### Task 14: Empty, error, and visual-system regression pass

**Files:**

- Modify: pages/components as needed from the pass

**Interfaces:**

- Consumes: all fixtures
- Produces: a UI that can be demoed without a backend

Checklist (every item is a real click-through, not a screenshot-only glance):

- [ ] Landing `/`: constellation hero, **Start building** → `/app`, no mosaic chrome.
- [ ] Hub `/app`: mosaic, four agent tiles non-link, empty KB allowed, CTAs work.
- [ ] Header mosaic on `/admin` while body is pastel; no pastel cards on Client; no mosaic hairlines on Admin category cards.
- [ ] Client empty KB: Ask disabled, exact copy.
- [ ] Client empty question: no job.
- [ ] All seven job statuses have labels.
- [ ] Timeline during a running job is openable.
- [ ] `CROSS` badge visible.
- [ ] Chip click → Sources highlight.
- [ ] Failed job: reason, no fake answer, PDF disabled.
- [ ] 404 job: *Job no longer available — please ask again.*
- [ ] Warnings banner uses §7.2 `warnings[]` only.
- [ ] PDF enabled only on completed + `pdf_available`.
- [ ] Admin 401 re-prompt.
- [ ] Admin 400/403 keep previous table.
- [ ] Auto-detect omits `category`.
- [ ] Chip `KB empty` when `getKb` fails.
- [ ] While a Client job is `queued` through `formatting`, chrome chip shows `Job running` on `/app` and `/admin` too; after complete/fail/404 it returns to KB state.

- [ ] **Step 1: Run the checklist against fixture mode.**

- [ ] **Step 2: Commit** `fix: close Pactlify UI empty and error states against fixtures`

---



### Task 15: Swap `api.ts` from fixtures to `fetch` (after backend Task 20)

**Files:**

- Modify: `outskillai/frontend/src/api.ts` **function bodies only**
- Keep: `frontend/src/fixtures/` as test data

**Interfaces:**

- Consumes: live `VITE_API_BASE_URL`, backend wire contract
- Produces: the same exported functions, now using `fetch`

```typescript
const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function parseError(res: Response): Promise<never> {
  const body = (await res.json()) as ApiErrorBody;
  throw { status: res.status, body };
}

export async function getKb(): Promise<KbInfo> {
  const res = await fetch(`${BASE}/kb`);
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function ingest(body: IngestRequest): Promise<IngestResult> {
  const token = getAdminToken();
  const payload: Record<string, unknown> = { folder_path: body.folder_path };
  if (body.category) payload.category = body.category; // omit when unset
  const res = await fetch(`${BASE}/admin/ingest`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(300_000),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}
```

Apply the same pattern to `getAdminStatus`, `getAdminDocuments`, `postQuery`, `getStatus`. `getReportPdf` uses `res.blob()` and does not force JSON.

Do not send the token on `/kb`, `/query`, `/status/*`, `/report/*`.

Optional: generate `types.ts` from `/openapi.json` and delete the hand-written duplicate.

- [ ] **Step 1: Replace fixture bodies with** `fetch`**. Leave a** `VITE_USE_FIXTURES=true` **escape hatch only if it is a single branch at the top of** `api.ts`**; default is live.**

- [ ] **Step 2: End-to-end against a running backend:** landing → Admin token → auto-detect folder path → table → Client question → Timeline while running → Answer + Sources → Download PDF. Confirm `GET /kb` drives the chip.

- [ ] **Step 3: Restart the API process, reload Admin, confirm empty table and disabled Ask; Client poll of an old** `job_id` **shows the 404 copy.**

- [ ] **Step 4: Commit** `feat: point Pactlify api.ts at the live FastAPI contract`

---



## Frontend tests / demo gate

No pytest here. The gate is the Task 14 checklist plus Task 15 end-to-end.

Demo script this UI must support (about 3 minutes, with backend running):

1. Open `/`. Mosaic landing and four agent tiles. Click **Load documents** or toggle Admin.
2. Enter the token. Leave category cards unselected (auto-detect). Paste the sample folder path, Submit. Table shows id, name, category, including one `uncategorized`.
3. Toggle Client (or **Ask the corpus**). Ask a question that needs both PM and Financial.
4. Open **Timeline** while it runs. Switch to **Answer**. Point at a `[c1]` chip → Sources highlight. Show a `CROSS` badge if present.
5. Click **Download PDF**.

---



## Frontend gotchas (do not regress)

- Two visual systems muddying into one theme: mosaic tokens only on landing/Client/header; pastel tokens only on Admin body.
- Admin table empty after toggle: hydrate from `GET /admin/documents`; keep `documentStore`.
- Sending `"uncategorized"` as ingest `category` stamps the whole folder unmarked and skips the classifier — omit the field instead.
- Banner must not merge `result.warnings` with top-level `warnings`.
- PDF button that invents a client-side PDF when `pdf_available` is false.
- Putting `ADMIN_TOKEN` or OpenRouter keys in Vite env besides `VITE_API_BASE_URL`.
- Calling `PATCH /admin/documents/{id}` from the first-slice table.
- Treating the Admin | Client toggle as authorization.
- A status chip that shows folder paths from `/kb` (the API must not send them; do not add a second call to fill them in).

---



## Deferred (frontend)

- Browser file-drop ingest.
- Row-level retag UI.
- Real login replacing the toggle.
- Client query history.
- Custom branded PDF layout (download still works on the minimal backend PDF).
- Finance-lead persona polish.

---



## Suggested execution

Frontend Tasks 1–14 do not wait on the backend. Task 15 waits on backend Task 20 in `Updated-Architecture-and-Build-Plan-v4.0_Opus5-app.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.
2. **Inline Execution** — this session, `executing-plans`, checkpoints after Tasks 6, 11, 14, 15.

