import type { StampCategory } from "../types";

const CARDS: { title: string; desc: string; stamp: StampCategory | null; dot: string }[] = [
  { title: "Financial", desc: "Budgets, ROI, operating cost.", stamp: "financial", dot: "coral" },
  { title: "Project Manager", desc: "Timeline, milestones, risks.", stamp: "pm", dot: "sky" },
  { title: "CapEx", desc: "Capital spend and assets.", stamp: "capex", dot: "mint" },
  { title: "Policy", desc: "Stamp the whole folder as policy.", stamp: "policy", dot: "lavender" },
  { title: "Auto-detect / unmarked", desc: "Classifier decides. Default.", stamp: null, dot: "gray" },
];

export default function CategoryCards({
  selected,
  onSelect,
}: {
  selected: StampCategory | null;
  onSelect: (stamp: StampCategory | null) => void;
}) {
  return (
    <div className="card-grid">
      {CARDS.map((card) => {
        const isAuto = card.stamp === null;
        const active = isAuto ? selected === null : selected === card.stamp;
        return (
          <button
            key={card.title}
            type="button"
            className={active ? "stamp-card selected" : "stamp-card"}
            onClick={() => onSelect(active && !isAuto ? null : card.stamp)}
          >
            <span className={`dot ${card.dot}`} />
            <h2>{card.title}</h2>
            <p>{card.desc}</p>
          </button>
        );
      })}
    </div>
  );
}
