import type { EntryEvent } from "@/lib/types";
import { FilterPill } from "./ui";
import RelativeTime from "./RelativeTime";

const utcStamp = (iso: string) => `${iso.slice(0, 16).replace("T", " ")} UTC`;

export const entryEventLabel = (e: EntryEvent) => (e.competition ? `${e.event.name} · ${e.competition}` : e.event.name);

/** Choose which event's entry list the Teams tab shows (crews differ per event), and say where it came from. */
export default function EntryEventPicker({ slug, events, selectedId }: { slug: string; events: EntryEvent[]; selectedId?: string }) {
  const selected = events.find((e) => e.event.id === selectedId) ?? events.find((e) => e.is_default) ?? events[0];
  if (!selected) return null;
  return (
    <section data-testid="entry-events">
      <nav aria-label="Event entry list" className="mb-4 flex flex-wrap gap-2">
        {events.map((e) => (
          <FilterPill key={e.event.id} href={`/series/${slug}?tab=teams&event=${e.event.id}`} active={e.event.id === selected.event.id}>
            {entryEventLabel(e)}
          </FilterPill>
        ))}
      </nav>
      <p className="mb-8 text-sm text-text-secondary" data-testid="entry-provenance">
        {selected.entry_count} cars · {selected.driver_count} drivers ·{" "}
        {selected.is_fixture ? "Fixture snapshot of the official entry list" : "Official entry list"}
        {selected.source_url && <> <a href={selected.source_url} target="_blank" rel="noreferrer" className="text-accent hover:underline">↗</a></>}
        {selected.checked_at && <> · checked <RelativeTime iso={selected.checked_at} fallback={utcStamp(selected.checked_at)} /></>}
      </p>
    </section>
  );
}
