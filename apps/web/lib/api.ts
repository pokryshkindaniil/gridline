import { cookies } from "next/headers";

import { apiUrl } from "./apiUrl";

/** Server-side fetch against the GRIDLINE API. Never cached: freshness is the product. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), { cache: "no-store", ...init });
  if (!res.ok) throw new ApiError(res.status, `${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function viewerTimezone(): Promise<string> {
  const tz = (await cookies()).get("gl_tz")?.value;
  return tz ? decodeURIComponent(tz) : "UTC";
}
