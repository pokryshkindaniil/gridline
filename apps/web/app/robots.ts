import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/seo";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Do not crawl calendar feed/API responses. Private management pages
      // remain crawlable so their page-level noindex directive can be read.
      disallow: ["/api/", "/api-proxy/"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
