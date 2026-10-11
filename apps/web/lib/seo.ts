import type { Metadata } from "next";

export const SITE_URL = "https://gridline-motorsport.vercel.app";
export const SITE_DESCRIPTION =
  "Follow Formula 1, FIA WEC and GT World Challenge Europe schedules. Subscribe to an automatically updated motorsport calendar for Google Calendar, Apple Calendar or Outlook.";

export function pageMetadata(title: string, path: string, description: string): Metadata {
  const url = new URL(path, SITE_URL).toString();
  return {
    title,
    description,
    alternates: { canonical: url },
    openGraph: {
      type: "website",
      siteName: "GRIDLINE",
      title: `${title} | GRIDLINE`,
      description,
      url,
    },
    twitter: {
      card: "summary_large_image",
      title: `${title} | GRIDLINE`,
      description,
    },
  };
}
