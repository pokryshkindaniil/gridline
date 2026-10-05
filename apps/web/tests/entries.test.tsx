import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EntryEventPicker, { entryEventLabel } from "@/components/EntryEventPicker";
import TeamRow from "@/components/TeamRow";
import type { Driver, EntryEvent, EventOut, Entry, Team } from "@/lib/types";

const drv = (first: string, last: string, nat = "GB"): Driver => ({ slug: `${first}-${last}`.toLowerCase(), first_name: first, last_name: last, nationality_code: nat, image_url: null });
const series = { slug: "gt-world-challenge-europe", name: "GT World Challenge Europe", short_name: "GTWC", category: "gt" as const, official_url: "", logo_url: null, active: true };
const car = (n: string, crew: Driver[], model = "M4 GT3 EVO") =>
  ({ race_number: n, vehicle: { manufacturer: "BMW", model, class_name: "Pro", race_number: n, image_url: null, fallback_logo_url: null }, drivers: crew }) satisfies Entry;
const team = (name: string, entries: Entry[]): Team => ({ slug: name.toLowerCase().replace(/ /g, "-"), name, short_name: null, logo_url: null, website_url: null, series, vehicle: entries[0]?.vehicle ?? null, entries });

const ev = (id: string, name: string): EventOut => ({ id, slug: id, name, series_slug: series.slug, series_short_name: "GTWC", year: 2026, circuit_name: null, city: null, country_code: null, timezone: "UTC", start_date: "2026-05-01", end_date: "2026-05-03", official_url: null, status: "scheduled" });
const entryEvent = (id: string, name: string, over: Partial<EntryEvent> = {}): EntryEvent => ({
  event: ev(id, name), competition: "Sprint Cup", entry_count: 44, driver_count: 88, source_name: "GT World Challenge Europe (SRO) (entry list)",
  source_url: "https://www.gt-world-challenge-europe.com/entry-list/2026/barcelona", checked_at: "2026-10-04T12:00:00Z", is_fixture: false, is_default: false, ...over,
});

describe("GTWC / WEC entries in the existing team grid", () => {
  it("Sprint Cup: a two-driver entry shows its number and both drivers; two cars stay two groups", () => {
    const wrt = team("Team WRT", [car("32", [drv("Charles", "Weerts"), drv("Kelvin", "Van der Linde")]), car("46", [drv("Valentino", "Rossi"), drv("Max", "Hesse")])]);
    const { container } = render(<TeamRow team={wrt} />);
    expect(container.querySelectorAll("[data-testid=entry-group]")).toHaveLength(2);
    const cards = container.querySelectorAll("[data-testid=driver-card][data-drivers='2']");
    expect(cards).toHaveLength(2);
    expect(within(cards[0] as HTMLElement).queryByText("32")).toBeNull();        // the number lives in the ENTRY column…
    expect(container.querySelector("[data-testid=race-number]")).toHaveTextContent("#32"); // …strong and first
    expect(screen.getByText("Weerts")).toBeInTheDocument();
    expect(container.querySelector("[data-testid=driver-grid]")).toBeNull();
  });

  it("Endurance Cup: three- and four-driver entries keep the endurance layout (4+ in two columns)", () => {
    const three = team("Optimum Motorsport", [car("4", [drv("Adam", "Smalley"), drv("Freddie", "Tomlinson"), drv("Harry", "George")], "720S GT3 EVO")]);
    const four = team("JMR", [car("0", [drv("A", "One"), drv("B", "Two"), drv("C", "Three"), drv("D", "Four")])]);
    const a = render(<TeamRow team={three} />);
    expect(a.container.querySelector("[data-testid=driver-card][data-drivers='3'] ul")!.className).not.toContain("grid-cols-2");
    a.unmount();
    const b = render(<TeamRow team={four} />);
    expect(b.container.querySelector("[data-testid=driver-card][data-drivers='4'] ul")!.className).toContain("grid-cols-2");
  });

  it("WEC: a multi-car team shows #50 and #51 as separate three-driver groups", () => {
    const af = team("Ferrari AF Corse", [
      car("50", [drv("Antonio", "Fuoco", "IT"), drv("Miguel", "Molina", "ES"), drv("Nicklas", "Nielsen", "DK")], "499P"),
      car("51", [drv("Alessandro", "Pier Guidi", "IT"), drv("James", "Calado"), drv("Antonio", "Giovinazzi", "IT")], "499P"),
    ]);
    const { container } = render(<TeamRow team={af} />);
    expect(container.querySelectorAll("[data-testid=entry-group]")).toHaveLength(2);
    expect(container.querySelectorAll("[data-testid=driver-card][data-drivers='3']")).toHaveLength(2);
    expect(screen.getByText("Pier Guidi")).toBeInTheDocument();
  });

  it("the same car shows a different crew when a different event's entry is rendered", () => {
    const at = (crew: Driver[]) => team("Boutsen VDS", [car("2", crew, "911 GT3 R")]);
    const barcelona = render(<TeamRow team={at([drv("Sven", "Müller"), drv("Dorian", "Boccolacci")])} />);
    expect(screen.getByText("Müller")).toBeInTheDocument();
    barcelona.unmount();
    render(<TeamRow team={at([drv("Dorian", "Boccolacci"), drv("Morris", "Schuring")])} />);
    expect(screen.queryByText("Müller")).toBeNull();
    expect(screen.getByText("Schuring")).toBeInTheDocument();
  });

  it("team links carry the shown event so the team page opens on the same lineup", () => {
    render(<TeamRow team={team("Team WRT", [car("32", [drv("A", "B")])])} eventId="abc" />);
    expect(screen.getByRole("link", { name: "Team WRT" })).toHaveAttribute("href", "/teams/team-wrt?series=gt-world-challenge-europe&event=abc");
  });
});

describe("EntryEventPicker", () => {
  const events = [
    entryEvent("e1", "Brands Hatch"),
    entryEvent("e2", "Monza", { competition: "Endurance Cup", entry_count: 57, driver_count: 171, is_default: true }),
  ];

  it("lists every event with its cup, marks the selected one and links by event id", () => {
    render(<EntryEventPicker slug={series.slug} events={events} selectedId="e1" />);
    const pills = within(screen.getByRole("navigation", { name: "Event entry list" })).getAllByRole("link");
    expect(pills.map((p) => p.textContent)).toEqual(["Brands Hatch · Sprint Cup", "Monza · Endurance Cup"]);
    expect(pills[0]).toHaveAttribute("aria-current", "true");
    expect(pills[1]).not.toHaveAttribute("aria-current");
    expect(pills[1]).toHaveAttribute("href", "/series/gt-world-challenge-europe?tab=teams&event=e2");
    expect(entryEventLabel(entryEvent("x", "Spa", { competition: null }))).toBe("Spa");
  });

  it("falls back to the default event and states the provenance", () => {
    render(<EntryEventPicker slug={series.slug} events={events} />);
    const p = screen.getByTestId("entry-provenance");
    expect(p).toHaveTextContent("57 cars · 171 drivers · Official entry list");
    expect(within(p).getByRole("link")).toHaveAttribute("href", events[1].source_url!);
    expect(p).toHaveTextContent("checked"); // relative time once mounted, a UTC stamp before that
  });

  it("labels fixture snapshots as such", () => {
    render(<EntryEventPicker slug={series.slug} events={[entryEvent("e1", "Monza", { is_fixture: true })]} selectedId="e1" />);
    expect(screen.getByTestId("entry-provenance")).toHaveTextContent("Fixture snapshot of the official entry list");
  });

  it("renders nothing without events", () => {
    const { container } = render(<EntryEventPicker slug={series.slug} events={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
