import Link from "next/link";
import { notFound } from "next/navigation";
import EntryEventPicker from "@/components/EntryEventPicker";
import SessionList from "@/components/SessionList";
import TeamRow from "@/components/TeamRow";
import { EmptyState, FilterPill, PageContainer, SectionHeader } from "@/components/ui";
import RelativeTime from "@/components/RelativeTime";
import { api, ApiError, viewerTimezone } from "@/lib/api";
import { CATEGORY_LABEL } from "@/lib/format";
import type { EntryEvent, SeriesDetail, SessionOut, Team } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return { title: slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) };
}

/** Season-wide rosters (no per-event entry lists): say where they come from, or that they are development seed data. */
function RosterNote({ teams }: { teams: Team[] }) {
  const src = teams.find((t) => t.source_name);
  return (
    <p className="mt-10 text-sm text-text-secondary" data-testid="roster-note">
      {src ? (
        <>
          Season roster from {src.source_url ? <a href={src.source_url} target="_blank" rel="noreferrer" className="text-accent hover:underline">{src.source_name} ↗</a> : src.source_name}
          {src.checked_at && <> · checked <RelativeTime iso={src.checked_at} fallback={src.checked_at.slice(0, 10)} /></>}.
          {src.is_fixture && " This is a captured fixture snapshot, not a live import."}
        </>
      ) : (
        "Team, car and driver data for this series is development seed data — illustrative and unverified."
      )}
    </p>
  );
}

export default async function SeriesPage({ params, searchParams }: {
  params: Promise<{ slug: string }>; searchParams: Promise<{ tab?: string; event?: string }>;
}) {
  const { slug } = await params;
  const { tab = "schedule", event } = await searchParams;
  const tz = await viewerTimezone();

  let series: SeriesDetail;
  try { series = await api<SeriesDetail>(`/series/${slug}`); }
  catch (e) { if (e instanceof ApiError && e.status === 404) notFound(); throw e; }

  const from = new Date(Date.now() - 3 * 3600 * 1000).toISOString();
  const entryEvents = tab === "teams" ? await api<EntryEvent[]>(`/series/${slug}/entry-events`) : [];
  const shown = entryEvents.find((e) => e.event.id === event) ?? entryEvents.find((e) => e.is_default);
  const [sessions, teams] = await Promise.all([
    tab === "teams" ? Promise.resolve([] as SessionOut[]) : api<SessionOut[]>(`/sessions?series=${slug}&from=${from}&limit=200`),
    tab === "teams" ? api<Team[]>(`/series/${slug}/teams${shown ? `?event_id=${shown.event.id}` : ""}`) : Promise.resolve([] as Team[]),
  ]);

  return (
    <PageContainer>
      <SectionHeader title={series.name} subtitle={`${CATEGORY_LABEL[series.category]} · ${series.next_event ? `Next: ${series.next_event.name}` : "No upcoming events"}`}>
        <div className="pt-1"><a href={series.official_url} target="_blank" rel="noreferrer" className="text-sm text-accent hover:underline">Official site ↗</a></div>
      </SectionHeader>
      <div className="mb-10 flex gap-2">
        <FilterPill href={`/series/${slug}`} active={tab !== "teams"}>Schedule</FilterPill>
        <FilterPill href={`/series/${slug}?tab=teams`} active={tab === "teams"}>Teams</FilterPill>
      </div>

      {tab === "teams" ? (
        teams.length === 0 ? (
          <EmptyState title="No team data yet" body="Rosters for this series haven't been added." />
        ) : (
          <>
            {entryEvents.length > 0 && <EntryEventPicker slug={slug} events={entryEvents} selectedId={shown?.event.id} />}
            <div>{teams.map((t) => <TeamRow key={t.slug} team={t} eventId={shown?.event.id} />)}</div>
            {entryEvents.length === 0 && <RosterNote teams={teams} />}
          </>
        )
      ) : (
        <SessionList sessions={sessions} initialTz={tz} showSeries={false} emptyTitle="No upcoming sessions" />
      )}
      <div className="mt-12"><Link href="/calendar/create" className="text-accent hover:underline">Subscribe to {series.short_name} in your calendar →</Link></div>
    </PageContainer>
  );
}
