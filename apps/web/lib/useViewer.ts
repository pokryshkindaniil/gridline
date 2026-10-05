"use client";

import { useSyncExternalStore } from "react";

const noop = () => () => {};

/** Browser timezone. `initial` (from the gl_tz cookie) is used for SSR/hydration, then the real zone takes over. */
export function useViewerTimezone(initial: string): string {
  return useSyncExternalStore(
    noop,
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    () => initial,
  );
}

let tick = 0;
function subscribeMinute(cb: () => void) {
  const id = setInterval(() => { tick = Date.now(); cb(); }, 30_000);
  return () => clearInterval(id);
}

/** Current time, refreshed every 30s, stable between ticks. SSR value is 0 (render with suppressHydrationWarning). */
export function useNow(): number {
  return useSyncExternalStore(subscribeMinute, () => (tick ||= Date.now()), () => 0);
}
