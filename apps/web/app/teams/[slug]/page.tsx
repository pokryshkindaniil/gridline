import Link from "next/link";
import { notFound } from "next/navigation";
import TeamRow from "@/components/TeamRow";
import { PageContainer } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { formatDateRange } from "@/lib/format";
import type { TeamDetail } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function TeamPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ event?: string; series?: string }> }) {
  const { slug } = await params;
  const { event, series } = await searchParams;
  const qs = new URLSearchParams();
  if (event) qs.set("event_id", event);
  if (series) qs.set("series", series);  // a team slug is only unique within its series
  let team: TeamDetail;
  try { team = await api<TeamDetail>(`/teams/${slug}${qs.size ? `?${qs}` : ""}`); }
  catch (e) { if (e instanceof ApiError && e.status === 404) notFound(); throw e; }

  return (
    <PageContainer>
      <p className="pt-12 text-sm text-text-secondary"><Link href={`/series/${team.series.slug}?tab=teams`} className="hover:text-text-primary">← {team.series.name}</Link></p>
      {team.event && <p className="mt-2 text-sm text-text-secondary" data-testid="team-event">Entry list: {team.event.name}</p>}
      <TeamRow team={team} link={false} />
      <section className="mt-6">
        <h2 className="mb-4 text-2xl font-semibold tracking-tight">Upcoming events</h2>
        {team.upcoming_events.length === 0 ? <p className="text-text-secondary">No upcoming events.</p> : (
          <ul className="divide-y divide-border/70">
            {team.upcoming_events.map((e) => (
              <li key={e.id} className="flex items-baseline justify-between gap-4 py-4">
                <span className="font-medium">{e.name}</span>
                <span className="tabular text-sm text-text-secondary">{formatDateRange(e.start_date, e.end_date)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </PageContainer>
  );
}
