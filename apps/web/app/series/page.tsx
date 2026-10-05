import SeriesCard from "@/components/SeriesCard";
import { PageContainer, SectionHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { seriesMedia } from "@/lib/media";
import type { SeriesDetail } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "Series" };

export default async function SeriesDirectory() {
  const all = await api<SeriesDetail[]>("/series");  // the API already hides series that are not public
  const live = all.filter((s) => s.active);
  const soon = all.filter((s) => !s.active);
  return (
    <PageContainer>
      <SectionHeader title="Series" subtitle="Championships GRIDLINE tracks, session by session." />
      <ul className="grid grid-cols-1 gap-5 pb-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="series-grid">
        {live.map((s) => <li key={s.slug} className="flex"><SeriesCard series={s} media={seriesMedia(s.slug)} /></li>)}
      </ul>
      {soon.length > 0 && (
        <p className="mt-8 text-sm text-text-secondary" data-testid="series-soon">Coming soon: {soon.map((s) => s.name).join(" · ")}</p>
      )}
    </PageContainer>
  );
}
