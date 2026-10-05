import SessionList from "@/components/SessionList";
import { FilterPill, PageContainer, SectionHeader } from "@/components/ui";
import { api, viewerTimezone } from "@/lib/api";
import type { SessionOut } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "Calendar" };

const DAYS = [{ d: 7, label: "7 days" }, { d: 14, label: "14 days" }, { d: 30, label: "30 days" }];
const TYPES = [{ k: "", l: "All sessions" }, { k: "qualifying", l: "Qualifying" }, { k: "race", l: "Races" }];

export default async function CalendarPage({ searchParams }: { searchParams: Promise<{ days?: string; type?: string }> }) {
  const sp = await searchParams;
  const days = Number(sp.days) || 14;
  const type = sp.type ?? "";
  const tz = await viewerTimezone();
  const from = new Date(Date.now() - 3 * 3600 * 1000), to = new Date(Date.now() + days * 86400 * 1000);
  const q = new URLSearchParams({ from: from.toISOString(), to: to.toISOString(), limit: "400" });
  if (type) q.set("session_type", type);
  const sessions = await api<SessionOut[]>(`/sessions?${q}`);
  const href = (d: number, t: string) => `/calendar?days=${d}${t ? `&type=${t}` : ""}`;

  return (
    <PageContainer>
      <SectionHeader title="Upcoming" subtitle={`Every tracked session in the next ${days} days.`} />
      <div className="mb-10 flex flex-wrap gap-x-6 gap-y-3">
        <div className="flex gap-2">{DAYS.map((x) => <FilterPill key={x.d} href={href(x.d, type)} active={days === x.d}>{x.label}</FilterPill>)}</div>
        <div className="flex gap-2">{TYPES.map((x) => <FilterPill key={x.k} href={href(days, x.k)} active={type === x.k}>{x.l}</FilterPill>)}</div>
      </div>
      <SessionList sessions={sessions} initialTz={tz} emptyTitle="Nothing in this window" />
    </PageContainer>
  );
}
