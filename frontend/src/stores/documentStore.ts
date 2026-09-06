import type { AdminStatus, DocumentInfo, FailedFile, FailedUrl, IngestResult } from "../types";

export interface DocumentStoreState {
  documents: DocumentInfo[];
  failed_files: FailedFile[];
  failed_urls: FailedUrl[];
  last_folder: string | null;
}

const empty: DocumentStoreState = {
  documents: [],
  failed_files: [],
  failed_urls: [],
  last_folder: null,
};

let state: DocumentStoreState = { ...empty };
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((fn) => fn());
}

export function getDocumentStore(): DocumentStoreState {
  return state;
}

export function subscribeDocumentStore(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function replaceFromIngest(result: IngestResult, folder: string): void {
  state = {
    documents: result.documents,
    failed_files: result.failed_files,
    failed_urls: result.failed_urls,
    last_folder: folder,
  };
  emit();
}

export function hydrateFromAdmin(docs: DocumentInfo[], status: AdminStatus): void {
  state = {
    documents: docs,
    failed_files: status.failed_files,
    failed_urls: status.failed_urls,
    last_folder: status.last_folder,
  };
  emit();
}

export function clearIfServerEmpty(docs: DocumentInfo[]): void {
  if (docs.length === 0) {
    state = { documents: [], failed_files: [], failed_urls: [], last_folder: null };
    emit();
  }
}
