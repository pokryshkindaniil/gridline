"use client";

import { CATEGORY_LABEL } from "@/lib/format";
import type { Series } from "@/lib/types";

export default function SeriesSelector({ series, selected, onChange }: {
  series: Series[]; selected: string[]; onChange: (slugs: string[]) => void;
}) {
  const toggle = (slug: string) => onChange(selected.includes(slug) ? selected.filter((s) => s !== slug) : [...selected, slug]);
  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {series.map((s) => {
        const on = selected.includes(s.slug);
        return (
          <li key={s.slug}>
            <button
              type="button" role="checkbox" aria-checked={on} disabled={!s.active} onClick={() => toggle(s.slug)}
              className={`flex w-full items-center justify-between rounded-2xl px-5 py-4 text-left transition-colors ${
                on ? "bg-accent-soft ring-2 ring-accent" : "bg-surface-muted hover:bg-border/60"
              } disabled:cursor-not-allowed disabled:opacity-50`}
            >
              <span>
                <span className="block font-medium">{s.name}</span>
                <span className="block text-sm text-text-secondary">{s.active ? CATEGORY_LABEL[s.category] : "Coming soon"}</span>
              </span>
              <span aria-hidden className={`grid h-6 w-6 place-items-center rounded-full text-sm ${on ? "bg-accent text-white" : "border border-border"}`}>
                {on ? "✓" : ""}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
