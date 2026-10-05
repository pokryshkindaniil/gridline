import type { Entry, Team } from "@/lib/types";
import { manufacturerLogo, teamLogo } from "@/lib/media";
import DriverCard from "./DriverCard";
import EntryInfo from "./EntryInfo";
import TeamIdentity from "./TeamIdentity";

const modelKey = (e: Entry) => [e.vehicle?.manufacturer, e.vehicle?.model, e.vehicle?.class_name].join("|");

// Formula entries share one vehicle description but retain separate driver cards.
export function groupEntries(entries: Entry[]): Entry[][] {
  const solo = entries.length > 1 && entries.every((e) => e.drivers.length <= 1) && new Set(entries.map(modelKey)).size === 1;
  return solo ? [entries] : entries.map((e) => [e]);
}

function DriverGrid({ entries }: { entries: Entry[] }) {
  return (
    <div className="grid w-full grid-cols-1 gap-x-6 gap-y-5 min-[480px]:grid-cols-2" data-testid="driver-grid">
      {entries.map((e) => <DriverCard key={e.race_number ?? e.drivers[0]?.slug} entry={e} />)}
    </div>
  );
}

function EntryGroup({ team, group }: { team: Team; group: Entry[] }) {
  const lead = group[0];
  const vehicle = lead.vehicle ?? team.vehicle;
  const solo = group.every((e) => e.drivers.length <= 1);
  return (
    <div className="contents" data-testid="entry-group">
      <div className="flex items-center">
        <EntryInfo number={solo ? null : lead.race_number} vehicle={vehicle} manufacturerLogoUrl={manufacturerLogo(vehicle?.manufacturer)?.src} />
      </div>
      <div className="flex items-center">
        {solo ? <DriverGrid entries={group} /> : <DriverCard entry={lead} showNumber={false} />}
      </div>
    </div>
  );
}

function teamManufacturer(team: Team): string | null {
  const makes = new Set((team.entries.length ? team.entries.map((e) => e.vehicle) : [team.vehicle]).map((v) => v?.manufacturer ?? null));
  return makes.size === 1 ? [...makes][0] : null;
}

export default function TeamRow({ team, link = true, eventId }: { team: Team; link?: boolean; eventId?: string }) {
  const groups = groupEntries(team.entries);
  const make = teamManufacturer(team);
  return (
    <article className="grid grid-cols-1 gap-x-8 gap-y-6 border-t border-border py-7 first:border-t-0 lg:grid-cols-[1fr_2fr_2fr] lg:min-h-[13.25rem]" data-testid="team-row">
      <TeamIdentity
        team={team} link={link} eventId={eventId}
        teamLogoUrl={teamLogo(team.slug, team.series.slug)?.src} manufacturerLogoUrl={manufacturerLogo(make)?.src} manufacturerName={make}
      />
      <div className="grid grid-cols-1 gap-x-8 gap-y-6 md:grid-cols-2 lg:col-span-2">
        {groups.map((g, i) => <EntryGroup key={g[0].race_number ?? i} team={team} group={g} />)}
      </div>
    </article>
  );
}
