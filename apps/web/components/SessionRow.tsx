import { formatTime } from "@/lib/format";
import type { SessionOut } from "@/lib/types";
import SourceStatus from "./SourceStatus";
import { SeriesBadge } from "./ui";

export default function SessionRow({ session: s, tz, showSeries = true, showSource = true }: {
  session: SessionOut; tz: string; showSeries?: boolean; showSource?: boolean;
}) {
  const cancelled = s.status === "cancelled";
  return (
    <li className="grid grid-cols-[3.75rem_1fr] gap-x-4 gap-y-1 border-t border-border/70 py-4 first:border-t-0 sm:grid-cols-[4.5rem_4.5rem_1fr_auto] sm:items-baseline sm:gap-x-6">
      <time dateTime={s.start_at} className={`tabular text-2xl font-semibold tracking-tight ${cancelled ? "text-text-secondary line-through" : ""}`}>
        {formatTime(s.start_at, tz)}
      </time>
      <div className="col-start-2 flex items-baseline gap-2 sm:col-start-auto">
        {showSeries && <SeriesBadge name={s.series.short_name} />}
        <span className="text-sm text-text-secondary sm:hidden">{s.event.name}</span>
      </div>
      <div className="col-start-2 sm:col-start-auto">
        <p className={`text-lg leading-snug ${cancelled ? "text-text-secondary line-through" : "font-medium"}`}>
          {s.name}
          {cancelled && <span className="ml-2 rounded bg-danger/10 px-1.5 py-0.5 text-xs font-medium text-danger no-underline">Cancelled</span>}
          {s.status === "delayed" && <span className="ml-2 rounded bg-warning/10 px-1.5 py-0.5 text-xs font-medium text-warning">Delayed</span>}
        </p>
        <p className="hidden text-sm text-text-secondary sm:block">
          {s.event.name}
          {s.event.circuit_name && <span> · {s.event.circuit_name}</span>}
        </p>
      </div>
      {showSource && (
        <SourceStatus
          checkedAt={s.checked_at} sourceName={s.source_name} sourceUrl={s.source_url} isFixture={s.is_fixture}
          className="col-start-2 sm:col-start-auto sm:text-right"
        />
      )}
    </li>
  );
}
