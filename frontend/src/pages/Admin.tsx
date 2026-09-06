import { useEffect, useState } from "react";
import "../theme/pastel.css";
import CategoryCards from "../components/CategoryCards";
import DocumentTable from "../components/DocumentTable";
import {
  CHOOSE_ONE_MESSAGE,
  NEED_ONE_MESSAGE,
  getAdminDocuments,
  getAdminStatus,
  getKb,
  ingest,
  setAdminToken,
  type ApiError,
} from "../api";
import {
  clearIfServerEmpty,
  getDocumentStore,
  hydrateFromAdmin,
  replaceFromIngest,
  subscribeDocumentStore,
} from "../stores/documentStore";
import type { StampCategory } from "../types";

function isApiError(error: unknown): error is ApiError {
  return typeof error === "object" && error !== null && "status" in error && "body" in error;
}

export default function Admin() {
  const [token, setToken] = useState<string>("");
  const [authed, setAuthed] = useState(false);
  const [stamp, setStamp] = useState<StampCategory | null>(null);
  const [folder, setFolder] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [fileKey, setFileKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [store, setStore] = useState(getDocumentStore());

  useEffect(() => subscribeDocumentStore(() => setStore(getDocumentStore())), []);

  async function withToken(next: string): Promise<void> {
    setAdminToken(next);
    try {
      const status = await getAdminStatus();
      const { documents } = await getAdminDocuments();
      if (documents.length === 0) clearIfServerEmpty(documents);
      else hydrateFromAdmin(documents, status);
      setFolder(status.last_folder ?? "");
      setAuthed(true);
      setError(null);
    } catch (caught) {
      setAdminToken(null);
      setAuthed(false);
      setError(isApiError(caught) ? caught.body.message : "Could not authenticate.");
    }
  }

  async function submit(): Promise<void> {
    const path = folder.trim();
    if (path && files.length) {
      setError(CHOOSE_ONE_MESSAGE);
      return;
    }
    if (!path && !files.length) {
      setError(NEED_ONE_MESSAGE);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body = stamp
        ? { folder_path: path || undefined, files, category: stamp }
        : { folder_path: path || undefined, files };
      const result = await ingest(body);
      replaceFromIngest(result, path || "uploaded files");
      setFiles([]);
      setFileKey((key) => key + 1);
      await getKb();
    } catch (caught) {
      if (isApiError(caught) && caught.status === 401) {
        setAdminToken(null);
        setAuthed(false);
        setError(caught.body.message);
      } else {
        setError(isApiError(caught) ? caught.body.message : "Ingest failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (!authed) {
    return (
      <div className="admin-body">
        <h1>Admin token</h1>
        <p className="desc">Held in memory for this tab. Not a login.</p>
        <div className="upload-panel">
          <input
            type="password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="ADMIN_TOKEN"
          />
          <button className="btn-primary" type="button" onClick={() => void withToken(token)}>
            Continue
          </button>
          {error ? <p className="fail-list">{error}</p> : null}
        </div>
      </div>
    );
  }

  return (
    <div className="admin-body">
      <h1>Load a folder</h1>
      <p className="desc">Use a server folder path or upload files — not both. Optional stamp. Table is in-memory; restart needs the source again.</p>
      <div className="upload-panel">
        <label>
          Folder path
          <input
            type="text"
            value={folder}
            onChange={(event) => {
              setFolder(event.target.value);
              if (files.length) {
                setFiles([]);
                setFileKey((key) => key + 1);
              }
            }}
            placeholder="/absolute/path/to/outskillai/sample_data"
          />
        </label>
        <label>
          Or upload files
          <input
            key={fileKey}
            type="file"
            multiple
            accept=".pdf,.csv,.txt,text/plain,application/pdf,text/csv"
            onChange={(event) => {
              const next = Array.from(event.target.files ?? []);
              setFiles(next);
              if (next.length) setFolder("");
            }}
          />
        </label>
        {files.length ? (
          <p className="note">{files.map((file) => file.name).join(", ")}</p>
        ) : null}
        <button
          className="btn-primary"
          type="button"
          disabled={busy || (!folder.trim() && !files.length)}
          onClick={() => void submit()}
        >
          {busy ? "Loading…" : "Submit"}
        </button>
        <p className="note">Choose one source. Auto-detect omits category. Never send uncategorized. Top-level pdf/csv/txt only.</p>
        {error ? <p className="fail-list">{error}</p> : null}
      </div>
      <CategoryCards selected={stamp} onSelect={setStamp} />
      <DocumentTable
        documents={store.documents}
        failedFiles={store.failed_files}
        failedUrls={store.failed_urls}
      />
    </div>
  );
}
