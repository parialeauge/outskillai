import type { DocumentInfo, FailedFile, FailedUrl } from "../types";

export default function DocumentTable({
  documents,
  failedFiles,
  failedUrls,
}: {
  documents: DocumentInfo[];
  failedFiles: FailedFile[];
  failedUrls: FailedUrl[];
}) {
  if (documents.length === 0) {
    return (
      <div>
        <p>No documents loaded.</p>
        <FailList failedFiles={failedFiles} failedUrls={failedUrls} />
      </div>
    );
  }
  return (
    <div>
      <table className="doc-table">
        <thead>
          <tr>
            <th>id</th>
            <th>name</th>
            <th>category</th>
            <th>type</th>
            <th>chunks</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.document_id}>
              <td className="mono">{doc.document_id}</td>
              <td>{doc.source}</td>
              <td>
                {doc.category}
                {doc.overridden ? " · override" : ""}
              </td>
              <td>{doc.type}</td>
              <td>{doc.chunk_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <FailList failedFiles={failedFiles} failedUrls={failedUrls} />
    </div>
  );
}

function FailList({
  failedFiles,
  failedUrls,
}: {
  failedFiles: FailedFile[];
  failedUrls: FailedUrl[];
}) {
  if (failedFiles.length === 0 && failedUrls.length === 0) return null;
  return (
    <ul className="fail-list">
      {failedFiles.map((item) => (
        <li key={item.name}>
          {item.name}: {item.reason}
        </li>
      ))}
      {failedUrls.map((item) => (
        <li key={item.url}>
          {item.url}: {item.reason}
        </li>
      ))}
    </ul>
  );
}
