import type { NextRequest } from "next/server";

// Same-origin proxy for browser → API calls. Resolved at RUNTIME from API_URL (Vercel: the service binding) (works in containers,
// no CORS, no API host baked into the bundle). Only the feed endpoints are reachable.
import { apiUrl } from "@/lib/apiUrl";

const ALLOWED = /^feeds(\/[A-Za-z0-9_-]+)?$/;
const FORWARD_REQUEST = ["content-type", "x-edit-token", "if-none-match"];
const FORWARD_RESPONSE = ["content-type", "retry-after", "etag"];

async function handler(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const joined = path.join("/");
  if (!ALLOWED.test(joined)) return new Response("Not found", { status: 404 });

  const headers = new Headers();
  for (const h of FORWARD_REQUEST) { const v = req.headers.get(h); if (v) headers.set(h, v); }
  // Preserve the real client IP for the API's rate limiter (API must run with TRUST_PROXY_HEADERS=true).
  // Right-most entry: the one our own trusted proxy (Vercel / the reverse proxy) set; entries to its left are caller-supplied.
  const ip = req.headers.get("x-forwarded-for")?.split(",").at(-1)?.trim();
  if (ip) headers.set("x-forwarded-for", ip);

  const hasBody = !["GET", "HEAD"].includes(req.method);
  const upstream = await fetch(apiUrl(joined), {
    method: req.method, headers, body: hasBody ? await req.text() : undefined, cache: "no-store",
  }).catch(() => null);
  if (!upstream) return new Response(JSON.stringify({ detail: "API unavailable" }), { status: 502, headers: { "content-type": "application/json" } });

  const out = new Headers();
  for (const h of FORWARD_RESPONSE) { const v = upstream.headers.get(h); if (v) out.set(h, v); }
  return new Response(upstream.status === 204 ? null : upstream.body, { status: upstream.status, headers: out });
}

export { handler as GET, handler as POST, handler as PATCH, handler as DELETE };
