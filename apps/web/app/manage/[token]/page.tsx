import ManageFeed from "@/components/ManageFeed";
import CalendarFeedCard from "@/components/CalendarFeedCard";
import { EmptyState, PageContainer, SectionHeader } from "@/components/ui";
import FreshnessList from "@/components/FreshnessList";
import { api, ApiError } from "@/lib/api";
import { formatDayHeading, TYPE_LABEL } from "@/lib/format";
import type { Change, Feed, Series, SourceHealth } from "@/lib/types";
import RelativeTime from "@/components/RelativeTime";

export const dynamic = "force-dynamic";
export const metadata = { title: "Manage your feed", robots: { index: false } };

function ChangeValue({ field, value }: { field: string; value: string | null }) {
  if (!value) return <>—</>;
  if (field === "start_at" || field === "end_at") {
    return <time dateTime={value}>{new Date(value).toISOString().slice(11, 16)} UTC</time>;
  }
  return <>{field === "session_type" ? TYPE_LABEL[value] ?? value : value}</>;
}

export default async function ManagePage({ params, searchParams }: {
  params: Promise<{ token: string }>; searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await params;
  const { token: editToken } = await searchParams;

  let feed: Feed;
  try {
    feed = await api<Feed>(`/feeds/${token}`);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 410)) {
      return (
        <PageContainer narrow>
          <SectionHeader title={e.status === 410 ? "Feed revoked" : "Feed not found"} />
          <EmptyState
            title={e.status === 410 ? "This calendar feed has been revoked." : "We couldn't find that feed."}
            body="Calendar apps subscribed to it will stop receiving updates. You can create a new feed at any time."
            action={<a href="/calendar/create" className="text-accent hover:underline">Create a new calendar →</a>}
          />
        </PageContainer>
      );
    }
    throw e;
  }

  const [allSeries, changes, health] = await Promise.all([
    api<Series[]>("/series"), api<Change[]>(`/feeds/${token}/changes?limit=8`), api<SourceHealth[]>("/sources/health"),
  ]);
  const slugs = new Set(feed.series.map((s) => s.slug));

  return (
    <PageContainer narrow>
      <SectionHeader title="Your calendar" subtitle={
        <span className="inline-flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-success" aria-hidden /> Active · {feed.series.map((s) => s.short_name).join(", ")} · {feed.session_types.map((t) => TYPE_LABEL[t]).join(", ")} · {feed.timezone}</span>
      } />
      <div className="space-y-14">
        <CalendarFeedCard webcalUrl={feed.webcal_url} httpUrl={feed.public_url} />

        <section>
          <h2 className="mb-1 text-2xl font-semibold tracking-tight">Data freshness</h2>
          <p className="mb-5 text-text-secondary">When each source was last checked successfully.</p>
          <FreshnessList sources={health.filter((h) => slugs.has(h.series))} />
        </section>

        <section>
          <h2 className="mb-1 text-2xl font-semibold tracking-tight">Recent changes</h2>
          <p className="mb-5 text-text-secondary">Schedule updates your calendar has already received.</p>
          {changes.length === 0 ? (
            <EmptyState title="No schedule changes yet" body="When a session moves, it appears here and your calendar updates in place." />
          ) : (
            <ul className="divide-y divide-border/70">
              {changes.map((c, i) => (
                <li key={i} className="py-4">
                  <p className="text-xs font-semibold tracking-wider text-text-secondary"><RelativeTime iso={c.detected_at} fallback={formatDayHeading(c.detected_at, "UTC")} /></p>
                  <p className="font-medium">{c.series_short_name} {c.event_name} · {c.session_name}</p>
                  <p className="tabular text-text-secondary">
                    {c.field_name === "status" ? "Status" : c.field_name === "start_at" ? "Start" : c.field_name}:{" "}
                    <ChangeValue field={c.field_name} value={c.old_value} /> → <ChangeValue field={c.field_name} value={c.new_value} />
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h2 className="mb-5 text-2xl font-semibold tracking-tight">Settings</h2>
          <ManageFeed feed={feed} allSeries={allSeries} editToken={editToken ?? null} />
        </section>
      </div>
    </PageContainer>
  );
}
