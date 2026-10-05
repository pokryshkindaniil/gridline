// API_URL is injected by Vercel and points to the private API service. Local
// development falls back to port 8000.
export const API_PREFIX = "/api";

export function apiUrl(path: string): string {
  const base = new URL(process.env.API_URL ?? "http://localhost:8000");
  const root = base.pathname.replace(/\/+$/, "");
  const prefix = root.endsWith(API_PREFIX) ? root : `${root}${API_PREFIX}`;
  return new URL(`${prefix}/${path.replace(/^\/+/, "")}`, base.origin).toString();
}
