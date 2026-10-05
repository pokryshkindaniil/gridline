import CreateCalendar from "@/components/CreateCalendar";
import { PageContainer, SectionHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { Series } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "Create your calendar" };

export default async function CreatePage() {
  const series = await api<Series[]>("/series");
  return (
    <PageContainer narrow>
      <SectionHeader title="Create your calendar" subtitle="Pick what you follow. We keep the schedule in sync." />
      <CreateCalendar series={series} />
    </PageContainer>
  );
}
