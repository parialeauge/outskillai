import { Link } from "react-router-dom";
import type { CSSProperties } from "react";

type Node = { x: number; y: number; r: number; live?: boolean };

const NODES: Node[] = [
  { x: 430, y: 90, r: 3.2 },
  { x: 520, y: 70, r: 2.6 },
  { x: 610, y: 110, r: 3.4 },
  { x: 700, y: 60, r: 2.8 },
  { x: 790, y: 95, r: 3.1 },
  { x: 880, y: 50, r: 2.4 },
  { x: 480, y: 180, r: 3 },
  { x: 590, y: 200, r: 2.7 },
  { x: 690, y: 165, r: 3.3 },
  { x: 800, y: 190, r: 2.9 },
  { x: 900, y: 150, r: 3.2 },
  { x: 980, y: 210, r: 2.5 },
  { x: 450, y: 280, r: 3.1 },
  { x: 560, y: 310, r: 2.8 },
  { x: 670, y: 270, r: 6, live: true },
  { x: 760, y: 300, r: 5.2, live: true },
  { x: 840, y: 255, r: 4.6, live: true },
  { x: 910, y: 320, r: 5.4, live: true },
  { x: 980, y: 280, r: 3.8, live: true },
  { x: 520, y: 400, r: 3 },
  { x: 630, y: 430, r: 2.7 },
  { x: 740, y: 390, r: 3.4 },
  { x: 850, y: 440, r: 2.9 },
  { x: 940, y: 400, r: 3.1 },
  { x: 1040, y: 360, r: 2.6 },
  { x: 600, y: 520, r: 2.8 },
  { x: 720, y: 540, r: 3.2 },
  { x: 830, y: 510, r: 2.7 },
  { x: 940, y: 560, r: 3 },
];

const EDGES: Array<[number, number]> = [
  [0, 1],
  [1, 2],
  [2, 3],
  [3, 4],
  [4, 5],
  [0, 6],
  [2, 7],
  [3, 8],
  [4, 9],
  [5, 10],
  [6, 7],
  [7, 8],
  [8, 9],
  [9, 10],
  [10, 11],
  [6, 12],
  [7, 13],
  [8, 14],
  [9, 15],
  [10, 16],
  [11, 18],
  [12, 13],
  [13, 14],
  [14, 15],
  [15, 16],
  [16, 17],
  [17, 18],
  [12, 19],
  [14, 20],
  [15, 21],
  [17, 22],
  [18, 24],
  [19, 20],
  [20, 21],
  [21, 22],
  [22, 23],
  [23, 24],
  [20, 25],
  [21, 26],
  [22, 27],
  [23, 28],
  [25, 26],
  [26, 27],
  [27, 28],
];

const TRUST = ["Financial", "PM", "CapEx", "General", "Cited PDF"] as const;

const FLOW = [
  { label: "Client", hint: "Asks a question" },
  { label: "UI Interface", hint: "Client workspace" },
  { label: "Multi-Agent Worker", hint: "Parent + specialists" },
  { label: "Tools", hint: "OpenRouter · web" },
  { label: "RAG Engine", hint: "Retrieve + cite" },
  { label: "Response and Report", hint: "Answer + PDF" },
] as const;

export default function ConstellationLanding() {
  return (
    <main className="constellation">
      <svg className="constellation-net constellation-svg" viewBox="0 0 1200 640" aria-hidden="true">
        {EDGES.map(([a, b]) => {
          const from = NODES[a];
          const to = NODES[b];
          const live = Boolean(from.live && to.live);
          return (
            <line
              key={`${a}-${b}`}
              className={live ? "constellation-edge live" : "constellation-edge"}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
            />
          );
        })}
        {NODES.map((node, index) =>
          node.live ? (
            <g key={index}>
              <circle className="constellation-halo" cx={node.x} cy={node.y} r={node.r * 2.4} />
              <circle className="constellation-node live" cx={node.x} cy={node.y} r={node.r} />
            </g>
          ) : (
            <circle
              key={index}
              className="constellation-node"
              cx={node.x}
              cy={node.y}
              r={node.r}
            />
          ),
        )}
      </svg>
      <div className="constellation-fade" />
      <header className="constellation-bar">
        <Link className="constellation-wordmark" to="/">
          Pactlify
        </Link>
      </header>
      <section className="constellation-copy">
        <p className="constellation-eyebrow">Multi-agent research</p>
        <h1>
          <span className="constellation-ask">Ask the</span>
          <br />
          <span className="constellation-sweep">Corpus</span>.
        </h1>
        <p className="constellation-sub">
          Pactlify loads a shared folder, then routes Financial, PM, CapEx, and General
          specialists. They retrieve, optionally search the live web, and cite what they used.
        </p>
        <div className="constellation-actions">
          <Link className="constellation-cta primary" to="/app">
            Start building
          </Link>
          <Link className="constellation-cta ghost" to="/admin">
            Load documents
          </Link>
        </div>
        <ul className="constellation-trust">
          {TRUST.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <ol className="constellation-flow" aria-label="How a question moves through Pactlify">
          {FLOW.map((step, index) => (
            <li key={step.label} className="constellation-flow-item" style={{ "--step": index } as CSSProperties}>
              {index > 0 ? <span className="constellation-flow-arrow" aria-hidden="true" /> : null}
              <div className="constellation-flow-block">
                <strong>{step.label}</strong>
                <span>{step.hint}</span>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
