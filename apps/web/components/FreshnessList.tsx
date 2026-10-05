import type { SourceHealth } from "@/lib/types";
import RelativeTime from "./RelativeTime";

const DOT: Record<string, string> = { healthy: "bg-success", degraded: "bg-warning", stale: "bg-warning", failing: "bg-danger", fixture_only: "bg-text-secondary/50" };
const LABEL: Record<string, string> = { healthy: "Healthy", degraded: "Partial data", stale: "Stale", failing: "Failing", fixture_only: "Fixture only" };

export default function FreshnessList({ sources }: { sources: SourceHealth[] }) {
  return (
    <ul className="divide-y divide-border/70">
      {sources.map((s) => (
        <li key={s.source_id} className="flex flex-col gap-1 py-4 sm:flex-row sm:items-baseline sm:justify-between">
          <div className="flex items-center gap-3">
            <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[s.status]}`} aria-hidden />
            <span className="font-medium">{s.source_name}</span>
            <span className="text-sm text-text-secondary">{LABEL[s.status]}</span>
          </div>
          <div className="pl-5 text-sm text-text-secondary sm:pl-0 sm:text-right">
            {s.last_successful_sync
              ? <>{s.live ? "verified " : "fixture loaded "}<RelativeTime iso={s.last_successful_sync} fallback="" /></>
              : "never verified"}
            {s.last_error && <p className="text-danger">{s.last_error}</p>}
          </div>
        </li>
      ))}
    </ul>
  );
}
