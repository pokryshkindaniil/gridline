import type { MetadataRoute } from "next";
import { api } from "@/lib/api";
import { SITE_URL } from "@/lib/seo";
import type { Series } from "@/lib/types";

// The public catalogue is data-driven, so newly enabled series appear here
// without listing inactive or private championships.
export const dynamic = "force-dynamic";

const PUBLIC_ROUTES = ["/", "/series", "/calendar", "/calendar/create", "/sources"];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const routes: MetadataRoute.Sitemap = PUBLIC_ROUTES.map((path) => ({
    url: new URL(path, SITE_URL).toString(),
  }));

  try {
    const series = await api<Series[]>("/series");
    const activeSlugs = new Set(
      series.filter((item) => item.active && /^[a-z0-9-]+$/.test(item.slug)).map((item) => item.slug),
    );
    for (const slug of activeSlugs) {
      routes.push({ url: new URL(`/series/${slug}`, SITE_URL).toString() });
    }
  } catch {
    // Keep the sitemap available when the schedule API is temporarily down.
    // The series directory still links to the public championship pages.
  }

  return routes;
}
