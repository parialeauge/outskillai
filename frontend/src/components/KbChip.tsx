import { useCallback, useEffect, useState } from "react";
import { getKb } from "../api";
import { getJobChip, subscribeJobChip } from "../stores/jobChipStore";

export default function KbChip() {
  const [kbText, setKbText] = useState("KB empty");
  const [job, setJob] = useState(getJobChip());

  const refreshKb = useCallback(async () => {
    try {
      const info = await getKb();
      setKbText(info.loaded ? `KB loaded · ${info.document_count} docs` : "KB empty");
    } catch {
      setKbText("KB empty");
    }
  }, []);

  useEffect(() => {
    void refreshKb();
    const id = window.setInterval(() => void refreshKb(), 5000);
    return () => window.clearInterval(id);
  }, [refreshKb]);

  useEffect(() => subscribeJobChip(() => setJob(getJobChip())), []);

  return <span className="kb-chip">{job ?? kbText}</span>;
}
