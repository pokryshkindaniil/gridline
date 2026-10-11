import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));

import { api } from "@/lib/api";
import robots from "@/app/robots";
import sitemap from "@/app/sitemap";
import { pageMetadata, SITE_URL } from "@/lib/seo";

const fetchSeries = vi.mocked(api);

beforeEach(() => {
  fetchSeries.mockReset();
});

describe("search discovery and canonical URLs", () => {
  it("uses the new production host for canonical and social URLs", () => {
    const metadata = pageMetadata("Race Calendar", "/calendar", "Upcoming sessions");
    expect(metadata.alternates?.canonical).toBe(`${SITE_URL}/calendar`);
    expect(metadata.openGraph?.url).toBe(`${SITE_URL}/calendar`);
    expect(metadata.description).toBe("Upcoming sessions");
  });

  it("publishes robots rules with a sitemap, without blocking noindex management pages", () => {
    const directives = robots();
    expect(directives.sitemap).toBe(`${SITE_URL}/sitemap.xml`);
    expect(directives.rules).toEqual({
      userAgent: "*",
      allow: "/",
      disallow: ["/api/", "/api-proxy/"],
    });
  });

  it("lists only enabled championship pages and canonical public routes", async () => {
    fetchSeries.mockResolvedValueOnce([
      { slug: "formula-1", active: true },
      { slug: "fia-wec", active: true },
      { slug: "gt-world-challenge-europe", active: true },
      { slug: "imsa-weathertech", active: false },
      { slug: "../manage/token", active: true },
      { slug: "formula-1", active: true },
    ]);
    const urls = (await sitemap()).map((route) => route.url);
    expect(urls).toContain(SITE_URL + "/");
    expect(urls).toContain(SITE_URL + "/calendar/create");
    expect(urls).toContain(SITE_URL + "/series/formula-1");
    expect(urls).toContain(SITE_URL + "/series/fia-wec");
    expect(urls).toContain(SITE_URL + "/series/gt-world-challenge-europe");
    expect(urls).not.toContain(SITE_URL + "/series/imsa-weathertech");
    expect(urls.filter((url) => url.endsWith("/series/formula-1"))).toHaveLength(1);
    expect(urls.some((url) => url.includes("/manage/") || url.includes("/api/"))).toBe(false);
    expect(fetchSeries).toHaveBeenCalledWith("/series");
  });

  it("keeps the public static sitemap available if the API fails", async () => {
    fetchSeries.mockRejectedValueOnce(new Error("API unavailable"));
    const urls = (await sitemap()).map((route) => route.url);
    expect(urls).toContain(SITE_URL + "/");
    expect(urls).toContain(SITE_URL + "/series");
    expect(urls).not.toContain(SITE_URL + "/series/formula-1");
  });
});
