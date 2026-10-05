"use client";

import { timeAgo } from "@/lib/format";
import { useNow } from "@/lib/useViewer";

export default function SourceStatus({
  checkedAt, sourceName, sourceUrl, isFixture, className = "",
}: { checkedAt: string; sourceName: string; sourceUrl: string; isFixture?: boolean; className?: string }) {
  const now = useNow();
  return (
    <span className={`text-xs leading-5 text-text-secondary ${className}`}>
      <span suppressHydrationWarning>{now ? `Verified ${timeAgo(checkedAt, now)}` : "Verified"}</span>
      {" · "}
      <a href={sourceUrl} target="_blank" rel="noreferrer" title={sourceName} className="underline-offset-2 hover:text-text-primary hover:underline">
        Official source ↗
      </a>
      {isFixture && <span className="ml-2 rounded bg-warning/10 px-1.5 py-0.5 font-medium text-warning" title={sourceName}>Dev data</span>}
    </span>
  );
}
