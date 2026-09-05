import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { getKb } from "../api";

const AGENTS = ["Financial", "PM", "CapEx", "General"] as const;

export default function Landing() {
  const [kb, setKb] = useState("KB empty");

  useEffect(() => {
    void getKb()
      .then((info) => setKb(info.loaded ? `KB loaded · ${info.document_count} docs` : "KB empty"))
      .catch(() => setKb("KB empty"));
  }, []);

  return (
    <main className="page">
      <section className="hero">
        <p className="hero-label">MULTI-AGENT RESEARCH</p>
        <h1>Ask the corpus.</h1>
        <p>Pactlify — ask the corpus; specialists cite what they used.</p>
      </section>
      <section className="bento">
        <Link className="tile large" to="/client">
          <span className="eyebrow">Client</span>
          <strong>Ask the corpus</strong>
        </Link>
        <Link className="tile large" to="/admin">
          <span className="eyebrow">Admin</span>
          <strong>Load documents</strong>
        </Link>
        {AGENTS.map((name) => (
          <div className="tile" key={name}>
            <span className="eyebrow">Agent</span>
            <strong>{name}</strong>
          </div>
        ))}
        <div className="tile">
          <span className="eyebrow">Status</span>
          <strong className="mono">{kb}</strong>
        </div>
      </section>
      <p className="footer-strip">Admin loads a folder. Clients only ask. No upload on this page.</p>
    </main>
  );
}
