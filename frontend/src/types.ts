export type Category = "financial" | "pm" | "capex" | "policy" | "uncategorized";
export type StampCategory = "financial" | "pm" | "capex" | "policy" | "uncategorized";
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
  folder_path?: string;
  files?: File[];
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

export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  queued: "QUEUED",
  routing: "ROUTING",
  running: "RUNNING",
  merging: "MERGING",
  formatting: "FORMATTING",
  completed: "COMPLETED",
  failed: "FAILED",
};
