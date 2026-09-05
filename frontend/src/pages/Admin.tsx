import { useEffect, useState } from "react";
import "../theme/pastel.css";
import CategoryCards from "../components/CategoryCards";
import DocumentTable from "../components/DocumentTable";
import {
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
    setBusy(true);
    setError(null);
    try {
      const body = stamp ? { folder_path: folder, category: stamp } : { folder_path: folder };
      const result = await ingest(body);
      replaceFromIngest(result, folder);
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
      <p className="desc">Optional stamp, then a server folder path. Table is in-memory; restart needs the path again.</p>
      <CategoryCards selected={stamp} onSelect={setStamp} />
      <div className="upload-panel">
        <label>
          Folder path
          <input type="text" value={folder} onChange={(event) => setFolder(event.target.value)} />
        </label>
        <button className="btn-primary" type="button" disabled={busy || !folder} onClick={() => void submit()}>
          {busy ? "Loading…" : "Submit"}
        </button>
        <p className="note">Auto-detect omits category. Never send uncategorized.</p>
        {error ? <p className="fail-list">{error}</p> : null}
      </div>
      <DocumentTable
        documents={store.documents}
        failedFiles={store.failed_files}
        failedUrls={store.failed_urls}
      />
    </div>
  );
}
