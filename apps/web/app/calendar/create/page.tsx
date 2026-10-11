import CreateCalendar from "@/components/CreateCalendar";
import { pageMetadata } from "@/lib/seo";
import { PageContainer, SectionHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { Series } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata = pageMetadata(
  "Subscribe to a Motorsport Calendar",
  "/calendar/create",
  "Create a personalised F1, WEC or GTWC calendar subscription. Choose your series, sessions and timezone, and receive schedule updates automatically.",
);

export default async function CreatePage() {
  const series = await api<Series[]>("/series");
  return (
    <PageContainer narrow>
      <SectionHeader title="Create your calendar" subtitle="Pick what you follow. We keep the schedule in sync." />
      <CreateCalendar series={series} />
    </PageContainer>
  );
}
