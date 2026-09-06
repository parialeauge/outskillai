import type { JobStatusPayload } from "../types";

export default function TimelineTab({ job }: { job: JobStatusPayload | null }) {
  const rows = job?.timeline ?? [];
  if (!rows.length) {
    return <p>No agent timeline yet.</p>;
  }
  return (
    <div>
      {rows.map((row) => (
        <div className="timeline-row" key={row.agent}>
          <strong>{row.agent}</strong>
          <div className="mono">{row.status}</div>
          <div>chunks {row.chunks_retrieved} · primary {row.primary_count}</div>
          <div>live web {row.used_live_web ? "yes" : "no"}</div>
          {row.error ? <div>{row.error}</div> : null}
        </div>
      ))}
    </div>
  );
}
