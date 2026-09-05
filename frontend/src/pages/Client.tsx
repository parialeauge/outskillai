import { useEffect, useState } from "react";
import AnswerTab from "../components/AnswerTab";
import SourcesTab from "../components/SourcesTab";
import TimelineTab from "../components/TimelineTab";
import { getKb, postQuery, getStatus, type ApiError } from "../api";
import { setJobChip } from "../stores/jobChipStore";
import { JOB_STATUS_LABELS, type JobStatus, type JobStatusPayload } from "../types";

const RUNNING: JobStatus[] = ["queued", "routing", "running", "merging", "formatting"];

function isApiError(error: unknown): error is ApiError {
  return typeof error === "object" && error !== null && "status" in error && "body" in error;
}

export default function Client() {
  const [loaded, setLoaded] = useState(false);
  const [question, setQuestion] = useState("");
  const [inline, setInline] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatusPayload | null>(null);
  const [lost, setLost] = useState(false);
  const [tab, setTab] = useState<"answer" | "timeline" | "sources">("answer");
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  useEffect(() => {
    void getKb()
      .then((info) => setLoaded(info.loaded))
      .catch(() => setLoaded(false));
  }, []);

  useEffect(() => {
    if (!jobId) return;
    let stop = false;
    async function poll(): Promise<void> {
      try {
        const payload = await getStatus(jobId!);
        if (stop) return;
        setJob(payload);
        setLost(false);
        if (RUNNING.includes(payload.status)) {
          setJobChip("Job running");
        } else {
          setJobChip(null);
        }
        if (payload.status === "completed" || payload.status === "failed") return;
        window.setTimeout(() => void poll(), 1000);
      } catch (error) {
        if (stop) return;
        setJobChip(null);
        if (isApiError(error) && error.status === 404) {
          setLost(true);
          setJob(null);
          return;
        }
      }
    }
    void poll();
    return () => {
      stop = true;
      setJobChip(null);
    };
  }, [jobId]);

  async function ask(): Promise<void> {
    const trimmed = question.trim();
    if (!trimmed) {
      setInline("Enter a question.");
      return;
    }
    setInline(null);
    setLost(false);
    try {
      const { job_id } = await postQuery(trimmed);
      setTab("answer");
      setJobId(job_id);
      setJobChip("Job running");
    } catch (error) {
      if (isApiError(error) && error.body.error === "kb_empty") {
        setLoaded(false);
        setInline("Knowledge base not loaded — ask admin.");
        return;
      }
      if (isApiError(error) && error.body.error === "empty_query") {
        setInline(error.body.message);
        return;
      }
      setInline(isApiError(error) ? error.body.message : "Could not start the job.");
    }
  }

  const askDisabled = !loaded;
  const statusLabel = job ? JOB_STATUS_LABELS[job.status] : lost ? "FAILED" : null;

  return (
    <div className="client-layout">
      <aside className="client-left">
        <p className="hero-label">QUERY</p>
        <textarea
          className="query-field"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask the corpus"
        />
        <button className="btn-primary" type="button" disabled={askDisabled} onClick={() => void ask()}>
          Ask
        </button>
        <p className="helper">Parent routes to Financial, PM, CapEx, General.</p>
        {askDisabled ? <p className="inline-error">Knowledge base not loaded — ask admin.</p> : null}
        {inline ? <p className="inline-error">{inline}</p> : null}
      </aside>
      <section className="client-right">
        {lost ? <p>Job no longer available — please ask again.</p> : null}
        {statusLabel ? <p className="status-label">{statusLabel}</p> : null}
        {job && job.warnings.length > 0 ? (
          <div className="banner">
            {job.warnings.map((warning) => (
              <div key={warning}>{warning}</div>
            ))}
          </div>
        ) : null}
        <div className="tabs">
          <button className={tab === "answer" ? "active" : ""} type="button" onClick={() => setTab("answer")}>
            Answer
          </button>
          <button className={tab === "timeline" ? "active" : ""} type="button" onClick={() => setTab("timeline")}>
            Timeline
          </button>
          <button className={tab === "sources" ? "active" : ""} type="button" onClick={() => setTab("sources")}>
            Sources
          </button>
        </div>
        {tab === "answer" ? (
          <AnswerTab
            job={job}
            lost={lost}
            onCiteClick={(id) => {
              setHighlightId(id);
              setTab("sources");
            }}
          />
        ) : null}
        {tab === "timeline" ? <TimelineTab job={job} /> : null}
        {tab === "sources" ? <SourcesTab job={job} highlightId={highlightId} /> : null}
      </section>
    </div>
  );
}
