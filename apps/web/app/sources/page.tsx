import FreshnessList from "@/components/FreshnessList";
import { pageMetadata } from "@/lib/seo";
import { PageContainer, SectionHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { SourceHealth } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata = pageMetadata(
  "Official Motorsport Schedule Sources",
  "/sources",
  "See where GRIDLINE gets its Formula 1, WEC and GTWC session times, source freshness and known limitations.",
);

export default async function SourcesPage() {
  const sources = await api<SourceHealth[]>("/sources/health");
  return (
    <PageContainer narrow>
      <SectionHeader title="Data sources" subtitle="Where every schedule comes from, and how fresh it is. Failures are shown, not hidden." />
      <FreshnessList sources={sources} />
      <div className="mt-14 space-y-6">
        {sources.map((s) => (
          <div key={s.source_id} className="rounded-2xl bg-surface-muted p-5">
            <p className="font-medium"><a href={s.official_url} target="_blank" rel="noreferrer" className="hover:underline">{s.source_name} ↗</a></p>
            <p className="mt-1 text-sm text-text-secondary">{s.live ? "Live adapter." : "Fixture-only: no live adapter yet."}{s.limitation ? ` ${s.limitation}` : ""}</p>
          </div>
        ))}
      </div>
    </PageContainer>
  );
}
