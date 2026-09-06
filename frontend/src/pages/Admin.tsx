import { useEffect, useState } from "react";
import "../theme/pastel.css";
import CategoryCards from "../components/CategoryCards";
import DocumentTable from "../components/DocumentTable";
import {
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
      const last = status.last_folder ?? "";
      setFolder(last.includes("pactlify_upload_") ? "" : last);
      setAuthed(true);
      setError(null);
    } catch (caught) {
      setAdminToken(null);
      setAuthed(false);
      setError(isApiError(caught) ? caught.body.message : "Could not authenticate.");
    }
  }

  async function submit(): Promise<void> {
    const path = files.length ? "" : folder.trim();
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
      <p className="desc">Upload any number of files, any type, with any category stamp. File uploads add to the knowledge base. A folder path replaces it. Table is in-memory; restart needs the source again.</p>
      <div className="upload-panel">
        <label>
          Folder path
          <input
            type="text"
            value={folder}
            onChange={(event) => setFolder(event.target.value)}
            placeholder="/absolute/path/to/outskillai/sample_data"
          />
        </label>
        <label>
          Upload files
          <input
            key={fileKey}
            type="file"
            multiple
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
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
        <p className="note">Pick as many files as you want. If files are selected they are ingested even when a folder path is also filled in.</p>
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
