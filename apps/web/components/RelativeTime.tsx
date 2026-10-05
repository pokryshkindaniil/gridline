"use client";

import { timeAgo } from "@/lib/format";
import { useNow } from "@/lib/useViewer";

export default function RelativeTime({ iso, fallback }: { iso: string; fallback: string }) {
  const now = useNow();
  return <time dateTime={iso} suppressHydrationWarning>{now ? timeAgo(iso, now) : fallback}</time>;
}
