import { getReportPdf } from "../api";
import { JOB_STATUS_LABELS, type JobStatusPayload } from "../types";

type Props = {
  job: JobStatusPayload | null;
  lost: boolean;
  pending: boolean;
  onCiteClick: (id: string) => void;
};

export default function AnswerTab({ job, lost, pending, onCiteClick }: Props) {
  const result = job?.result ?? null;
  const pdfReady = job?.status === "completed" && result?.pdf_available === true;
  const citations = new Map((result?.citations ?? []).map((item) => [item.id, item]));

  async function download(): Promise<void> {
    if (!job || !pdfReady) return;
    try {
      const blob = await getReportPdf(job.job_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `pactlify-${job.job_id}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      /* stay without a fake PDF */
    }
  }

  if (lost) {
    return <p>Job no longer available — please ask again.</p>;
  }
  if (pending) {
    const label = job ? JOB_STATUS_LABELS[job.status] : "Working";
    return (
      <div className="answer-progress" role="status" aria-live="polite" aria-busy="true">
        <div className="progress-track" aria-hidden="true">
          <div className="progress-bar" />
        </div>
        <p className="progress-label">{label}</p>
      </div>
    );
  }
  if (job?.status === "failed") {
    return (
      <div className="answer-head">
        <p>{job.error ?? "The job failed."}</p>
        <button className="btn-primary" type="button" disabled>
          Download PDF
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="answer-head">
        {result?.answer.summary ? <p>{result.answer.summary}</p> : null}
        <button className="btn-primary" type="button" disabled={!pdfReady} onClick={() => void download()}>
          Download PDF
        </button>
      </div>
      {result?.answer.sections.map((section) => (
        <article className="section-block" key={section.agent}>
          <h2>{section.title}</h2>
          <p>{section.body}</p>
          <ul>
            {section.key_points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
          <div>
            {section.citation_ids.map((id) => (
              <button key={id} className="cite" type="button" onClick={() => onCiteClick(id)}>
                [{id}]
                {citations.get(id)?.cross_category ? <span className="cross">CROSS</span> : null}
              </button>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}
