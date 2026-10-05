import { afterEach, describe, expect, it } from "vitest";
import { apiUrl } from "@/lib/apiUrl";

const saved = process.env.API_URL;
afterEach(() => { if (saved === undefined) delete process.env.API_URL; else process.env.API_URL = saved; });

describe("apiUrl (runtime API_URL, canonical /api prefix)", () => {
  it("always targets /api/*, whether the bound origin has a trailing slash or not", () => {
    for (const base of ["https://internal.example", "https://internal.example/"]) {
      process.env.API_URL = base;
      expect(apiUrl("/series?x=1")).toBe("https://internal.example/api/series?x=1");
      expect(apiUrl("feeds/abc")).toBe("https://internal.example/api/feeds/abc");
    }
  });
  it("never produces /api/api when the base already ends in /api", () => {
    process.env.API_URL = "https://internal.example/api";
    expect(apiUrl("/health")).toBe("https://internal.example/api/health");
    process.env.API_URL = "https://internal.example/api/";
    expect(apiUrl("health")).toBe("https://internal.example/api/health");
  });
  it("falls back to the local API (also what Docker Compose uses with http://api:8000)", () => {
    delete process.env.API_URL;
    expect(apiUrl("/health")).toBe("http://localhost:8000/api/health");
    process.env.API_URL = "http://api:8000";
    expect(apiUrl("/series")).toBe("http://api:8000/api/series");
  });
  it("keeps query strings and encoded path segments intact", () => {
    process.env.API_URL = "https://i.example";
    expect(apiUrl("/teams/team-wrt?series=fia-wec&event_id=abc")).toBe("https://i.example/api/teams/team-wrt?series=fia-wec&event_id=abc");
  });
});
