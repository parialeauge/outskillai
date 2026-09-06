let jobLabel: string | null = null;
const listeners = new Set<() => void>();

export function setJobChip(label: string | null): void {
  jobLabel = label;
  listeners.forEach((l) => l());
}

export function getJobChip(): string | null {
  return jobLabel;
}

export function subscribeJobChip(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
