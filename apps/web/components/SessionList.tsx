"use client";

import { formatDayHeading, isoDay } from "@/lib/format";
import type { SessionOut } from "@/lib/types";
import { useViewerTimezone } from "@/lib/useViewer";
import SessionRow from "./SessionRow";
import { EmptyState } from "./ui";

/** Chronological schedule grouped by day in the viewer's timezone. */
export default function SessionList({ sessions, initialTz = "UTC", showSeries = true, emptyTitle = "Nothing scheduled", emptyBody }: {
  sessions: SessionOut[]; initialTz?: string; showSeries?: boolean; emptyTitle?: string; emptyBody?: string;
}) {
  const tz = useViewerTimezone(initialTz);
  if (sessions.length === 0) return <EmptyState title={emptyTitle} body={emptyBody} />;

  const days = new Map<string, SessionOut[]>();
  for (const s of sessions) {
    const key = isoDay(s.start_at, tz);
    days.set(key, [...(days.get(key) ?? []), s]);
  }
  return (
    <div className="space-y-10">
      <p className="text-sm text-text-secondary">Times shown in {tz.replace("_", " ")}</p>
      {[...days.entries()].map(([day, rows]) => (
        <section key={day} aria-labelledby={`d-${day}`}>
          <h2 id={`d-${day}`} className="mb-1 text-sm font-semibold tracking-wider text-text-secondary">
            {formatDayHeading(rows[0].start_at, tz)}
          </h2>
          <ul>{rows.map((s) => <SessionRow key={s.id} session={s} tz={tz} showSeries={showSeries} />)}</ul>
        </section>
      ))}
    </div>
  );
}
