import SessionList from "@/components/SessionList";
import { FilterPill, PageContainer, SectionHeader } from "@/components/ui";
import { api, viewerTimezone } from "@/lib/api";
import { formatDateRange } from "@/lib/format";
import type { Weekend } from "@/lib/types";

export const dynamic = "force-dynamic";

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
    </PageContainer>
  );
}
