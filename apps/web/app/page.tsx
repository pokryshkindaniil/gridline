import SessionList from "@/components/SessionList";
import Link from "next/link";
import { pageMetadata, SITE_DESCRIPTION } from "@/lib/seo";
import { FilterPill, PageContainer, SectionHeader } from "@/components/ui";
import { api, viewerTimezone } from "@/lib/api";
import { formatDateRange } from "@/lib/format";
import type { Weekend } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata = pageMetadata("Motorsport Calendar for F1, WEC & GTWC", "/", SITE_DESCRIPTION);

const FILTERS = [
  { key: "", label: "All" }, { key: "formula", label: "Formula" }, { key: "endurance", label: "Endurance" },
  { key: "gt", label: "GT" }, { key: "rally", label: "Rally" }, { key: "moto", label: "Moto" },
];

export default async function ThisWeekend({ searchParams }: { searchParams: Promise<{ category?: string }> }) {
  const { category = "" } = await searchParams;
  const tz = await viewerTimezone();
  const w = await api<Weekend>(`/weekend?tz=${encodeURIComponent(tz)}${category ? `&category=${category}` : ""}`);

  return (
    <PageContainer>
      <SectionHeader
        title="This weekend"
        subtitle={
          <>
            {formatDateRange(w.start_date, w.end_date)}
            <br className="sm:hidden" />
            <span className="hidden sm:inline"> · </span>
            {w.session_count} session{w.session_count === 1 ? "" : "s"} across {w.series_count} series
          </>
        }
      />
      <div className="-mx-5 mb-10 flex gap-2 overflow-x-auto px-5 pb-1 sm:mx-0 sm:px-0">
        {FILTERS.map((f) => (
          <FilterPill key={f.key} href={f.key ? `/?category=${f.key}` : "/"} active={category === f.key}>{f.label}</FilterPill>
        ))}
      </div>
      <SessionList
        sessions={w.sessions}
        initialTz={tz}
        emptyTitle="No sessions this weekend"
        emptyBody={category ? "Nothing in this category — try All." : "Nothing is scheduled for these days in the sources GRIDLINE tracks."}
      />
      <section className="mt-14 max-w-3xl text-sm text-text-secondary" aria-label="About GRIDLINE">
        <h2 className="mb-2 text-lg font-semibold text-text-primary">One calendar for motorsport</h2>
        <p>
          Track Formula 1, FIA World Endurance Championship and GT World Challenge Europe
          sessions, from practice and qualifying to the race. Subscribe once in
          Google Calendar, Apple Calendar or Outlook. GRIDLINE keeps your
          calendar up to date when official schedules change.
        </p>
        <Link href="/calendar/create" className="mt-3 inline-block text-accent hover:underline">
          Create your motorsport calendar →
        </Link>
      </section>
    </PageContainer>
  );
}
