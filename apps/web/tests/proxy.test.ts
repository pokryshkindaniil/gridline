// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { GET, POST, DELETE } from "@/app/api-proxy/[...path]/route";

const ctx = (...path: string[]) => ({ params: Promise.resolve({ path }) });
const req = (method: string, url: string, init: RequestInit = {}) => new Request(`http://web${url}`, { method, ...init }) as never;

afterEach(() => vi.restoreAllMocks());

describe("/api-proxy", () => {
  it("only exposes the feed endpoints", async () => {
    const spy = vi.spyOn(globalThis, "fetch");
    for (const p of [["sources", "health"], ["feeds", "a", "b"], ["..", "etc"], ["calendar", "x.ics"], ["feeds", "a b"]]) {
      expect((await GET(req("GET", "/x"), ctx(...p))).status).toBe(404);
    }
    expect(spy).not.toHaveBeenCalled();
  });

  it("forwards edit token + body but not cookies, and relays rate-limit headers", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response('{"detail":"too many requests"}', { status: 429, headers: { "retry-after": "7", "content-type": "application/json", "set-cookie": "x=1" } }),
    );
    const res = await POST(req("POST", "/x", { body: "{}", headers: { "content-type": "application/json", cookie: "secret=1", "x-edit-token": "tok" } }), ctx("feeds"));
    expect(res.status).toBe(429);
    expect(res.headers.get("retry-after")).toBe("7");
    expect(res.headers.get("set-cookie")).toBeNull();
    const sent = spy.mock.calls[0][1]!.headers as Headers;
    expect(sent.get("x-edit-token")).toBe("tok");
    expect(sent.get("cookie")).toBeNull();
  });

  it("returns 204 without a body and 502 when the API is down", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(null, { status: 204 }));
    expect((await DELETE(req("DELETE", "/x"), ctx("feeds", "abc123"))).status).toBe(204);
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new Error("ECONNREFUSED"));
    expect((await GET(req("GET", "/x"), ctx("feeds", "abc123"))).status).toBe(502);
  });
});
