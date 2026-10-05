"use client";

import { TYPE_LABEL } from "@/lib/format";
import type { SessionType } from "@/lib/types";

export const SELECTABLE_TYPES: SessionType[] = ["practice", "qualifying", "sprint", "race"];

export default function SessionTypeSelector({ selected, onChange }: { selected: SessionType[]; onChange: (t: SessionType[]) => void }) {
  const toggle = (t: SessionType) => onChange(selected.includes(t) ? selected.filter((x) => x !== t) : [...selected, t]);
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Session types">
      {SELECTABLE_TYPES.map((t) => (
        <button
          key={t} type="button" aria-pressed={selected.includes(t)} onClick={() => toggle(t)}
          className={`rounded-full px-5 py-2 text-sm font-medium transition-colors ${
            selected.includes(t) ? "bg-text-primary text-background" : "bg-surface-muted text-text-secondary hover:text-text-primary"
          }`}
        >
          {TYPE_LABEL[t]}
        </button>
      ))}
    </div>
  );
}
