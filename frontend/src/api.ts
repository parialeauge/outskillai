import { getAdminToken, setAdminToken } from "./stores/tokenStore";
import type {
  AdminStatus,
  ApiErrorBody,
  DocumentInfo,
  IngestRequest,
  IngestResult,
  JobStatusPayload,
  KbInfo,
} from "./types";
import kbEmpty from "./fixtures/kb-empty.json";
import kbLoaded from "./fixtures/kb-loaded.json";
import adminStatusEmpty from "./fixtures/admin-status-empty.json";
import adminStatusLoaded from "./fixtures/admin-status-loaded.json";
import adminDocuments from "./fixtures/admin-documents.json";
import ingestSuccess from "./fixtures/ingest-success.json";
import jobQueued from "./fixtures/job-queued.json";
import jobRouting from "./fixtures/job-routing.json";
import jobRunning from "./fixtures/job-running.json";
import jobMerging from "./fixtures/job-merging.json";
import jobFormatting from "./fixtures/job-formatting.json";
import jobCompletedMulti from "./fixtures/job-completed-multi.json";
import jobCross from "./fixtures/job-cross.json";
import jobAgentFailed from "./fixtures/job-agent-failed.json";
import jobDropped from "./fixtures/job-dropped-citation.json";
import jobFailed from "./fixtures/job-failed.json";

export { setAdminToken, getAdminToken };

export type ApiError = { status: number; body: ApiErrorBody };

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const USE_FIXTURES = import.meta.env.VITE_USE_FIXTURES === "true";

let kbIsLoaded = false;
let pollTick = 0;

const CYCLE: JobStatusPayload[] = [
  jobQueued as JobStatusPayload,
  jobRouting as JobStatusPayload,
  jobRunning as JobStatusPayload,
  jobMerging as JobStatusPayload,
  jobFormatting as JobStatusPayload,
  jobCompletedMulti as JobStatusPayload,
];

function fail(status: number, error: string, message: string): never {
  const err: ApiError = { status, body: { error, message } };
  throw err;
}

function requireToken(): string {
  const token = getAdminToken();
  if (!token) {
    fail(401, "unauthorized", "Missing or wrong admin token.");
  }
  return token;
}

export async function getKb(): Promise<KbInfo> {
  if (USE_FIXTURES) {
    return (kbIsLoaded ? kbLoaded : kbEmpty) as KbInfo;
  }
  const res = await fetch(`${BASE}/kb`);
  if (!res.ok) await parseError(res);
  return res.json() as Promise<KbInfo>;
}

export async function getAdminStatus(): Promise<AdminStatus> {
  if (USE_FIXTURES) {
    requireToken();
    return (kbIsLoaded ? adminStatusLoaded : adminStatusEmpty) as AdminStatus;
  }
  const res = await fetch(`${BASE}/admin/status`, { headers: authHeaders() });
  if (!res.ok) await parseError(res);
  return res.json() as Promise<AdminStatus>;
}

export async function getAdminDocuments(): Promise<{ documents: DocumentInfo[] }> {
  if (USE_FIXTURES) {
    requireToken();
    return kbIsLoaded
      ? (adminDocuments as { documents: DocumentInfo[] })
      : { documents: [] };
  }
  const res = await fetch(`${BASE}/admin/documents`, { headers: authHeaders() });
  if (!res.ok) await parseError(res);
  return res.json() as Promise<{ documents: DocumentInfo[] }>;
}

export const CHOOSE_ONE_MESSAGE = "Choose a folder path or upload files, not both.";
export const NEED_ONE_MESSAGE = "Provide a folder path or upload files.";

export async function ingest(body: IngestRequest): Promise<IngestResult> {
  const folder = (body.folder_path ?? "").trim();
  const files = body.files ?? [];
  if (USE_FIXTURES) {
    if (folder === "__unauth__") {
      fail(401, "unauthorized", "Missing or wrong admin token.");
    }
    requireToken();
    if (folder && files.length) {
      fail(400, "choose_one", CHOOSE_ONE_MESSAGE);
    }
    if (!folder && !files.length) {
      fail(400, "bad_folder", NEED_ONE_MESSAGE);
    }
    if (folder === "__empty__") {
      fail(400, "bad_folder", "Folder is empty or missing — scan is top-level files only.");
    }
    if (folder === "__forbidden__") {
      fail(403, "forbidden_path", "Path is outside ALLOWED_INGEST_ROOT.");
    }
    kbIsLoaded = true;
    return ingestSuccess as IngestResult;
  }
  const token = getAdminToken();
  if (folder && files.length) {
    fail(400, "choose_one", CHOOSE_ONE_MESSAGE);
  }
  if (files.length) {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file, file.name);
    }
    if (body.category) form.append("category", body.category);
    const res = await fetch(`${BASE}/admin/ingest`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
      signal: AbortSignal.timeout(300_000),
    });
    if (!res.ok) await parseError(res);
    return res.json() as Promise<IngestResult>;
  }
  const payload: Record<string, unknown> = { folder_path: folder };
  if (body.category) payload.category = body.category;
  const res = await fetch(`${BASE}/admin/ingest`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(300_000),
  });
  if (!res.ok) await parseError(res);
  return res.json() as Promise<IngestResult>;
}

export async function postQuery(query: string): Promise<{ job_id: string }> {
  if (USE_FIXTURES) {
    if (!query.trim()) {
      fail(400, "empty_query", "Query must not be empty.");
    }
    if (!kbIsLoaded) {
      fail(409, "kb_empty", "Knowledge base not loaded — ask admin.");
    }
    pollTick = 0;
    return { job_id: "job_fixture" };
  }
  const res = await fetch(`${BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) await parseError(res);
  return res.json() as Promise<{ job_id: string }>;
}

export async function getStatus(jobId: string): Promise<JobStatusPayload> {
  if (USE_FIXTURES) {
    if (jobId !== "job_fixture") {
      fail(404, "job_not_found", "Job no longer available — please ask again.");
    }
    const override = localStorage.getItem("PACTLIFY_FIXTURE");
    if (override === "gone") {
      fail(404, "job_not_found", "Job no longer available — please ask again.");
    }
    if (override === "cross") return jobCross as JobStatusPayload;
    if (override === "agent-failed") return jobAgentFailed as JobStatusPayload;
    if (override === "dropped") return jobDropped as JobStatusPayload;
    if (override === "failed") return jobFailed as JobStatusPayload;
    const index = Math.min(pollTick, CYCLE.length - 1);
    pollTick += 1;
    return CYCLE[index];
  }
  const res = await fetch(`${BASE}/status/${jobId}`);
  if (!res.ok) await parseError(res);
  return res.json() as Promise<JobStatusPayload>;
}

export async function getReportPdf(jobId: string): Promise<Blob> {
  if (USE_FIXTURES) {
    if (jobId !== "job_fixture") {
      fail(404, "job_not_found", "Job no longer available — please ask again.");
    }
    const override = localStorage.getItem("PACTLIFY_FIXTURE");
    if (override === "failed" || override === "gone") {
      fail(404, "pdf_not_ready", "PDF is not available for this job.");
    }
    return new Blob(["%PDF-1.1\n%Pactlify fixture\n"], { type: "application/pdf" });
  }
  const res = await fetch(`${BASE}/report/${jobId}/pdf`);
  if (!res.ok) await parseError(res);
  return res.blob();
}

function authHeaders(): HeadersInit {
  return { Authorization: `Bearer ${getAdminToken() ?? ""}` };
}

async function parseError(res: Response): Promise<never> {
  try {
    const parsed = (await res.json()) as Record<string, unknown>;
    const detail = parsed.detail;
    const nested = typeof detail === "object" && detail !== null ? (detail as Record<string, unknown>) : null;
    const error = String(parsed.error || nested?.error || "error");
    const message = String(
      parsed.message || nested?.message || (typeof detail === "string" ? detail : "") || res.statusText || "Request failed.",
    );
    fail(res.status, error, message);
  } catch (caught) {
    if (caught && typeof caught === "object" && "status" in caught) {
      throw caught;
    }
    fail(res.status, "error", res.statusText || "Request failed.");
  }
}
