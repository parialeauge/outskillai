import type { JobStatusPayload } from "../types";

export default function SourcesTab({
  job,
  highlightId,
}: {
  job: JobStatusPayload | null;
  highlightId: string | null;
}) {
  const citations = job?.result?.citations ?? [];
  if (!citations.length) {
    return <p>No sources yet.</p>;
  }
  return (
    <div>
      {citations.map((item) => (
        <div
          className={item.id === highlightId ? "source-row highlight" : "source-row"}
          id={`source-${item.id}`}
          key={item.id}
        >
          <div className="mono">
            {item.id}
            {item.cross_category ? <span className="cross">CROSS</span> : null}
          </div>
          <div>{item.source}</div>
          <div>
            {item.type} · {item.category}
            {item.page != null ? ` · p.${item.page}` : ""}
            {item.row_start != null ? ` · rows ${item.row_start}–${item.row_end}` : ""}
          </div>
          <pre className="quote">{item.quote}</pre>
        </div>
      ))}
    </div>
  );
}
