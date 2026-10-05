"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Mirrors the browser timezone into a cookie so server components can bucket days correctly. */
export default function TimezoneSync() {
  const router = useRouter();
  useEffect(() => {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (!tz) return;
    const current = document.cookie.split("; ").find((c) => c.startsWith("gl_tz="))?.split("=")[1];
    if (current !== encodeURIComponent(tz)) {
      document.cookie = `gl_tz=${encodeURIComponent(tz)}; path=/; max-age=31536000; samesite=lax`;
      router.refresh();
    }
  }, [router]);
  return null;
}
