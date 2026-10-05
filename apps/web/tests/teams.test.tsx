import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import TeamRow, { groupEntries } from "@/components/TeamRow";
import type { Driver, Entry, Team, Vehicle } from "@/lib/types";

const drv = (slug: string, first: string, last: string): Driver => ({ slug, first_name: first, last_name: last, nationality_code: "GB", image_url: null });
const veh = (over: Partial<Vehicle> = {}): Vehicle => ({ manufacturer: "Ferrari", model: "SF-26", class_name: null, race_number: null, image_url: null, fallback_logo_url: null, ...over });
const series = { slug: "s", name: "Formula 1", short_name: "F1", category: "formula" as const, official_url: "", logo_url: null, active: true };
const team = (name: string, entries: Entry[]): Team => ({ slug: name.toLowerCase(), name, short_name: null, logo_url: null, website_url: null, series, vehicle: entries[0]?.vehicle ?? null, entries });

const f1 = (name: string, a: [string, string, string], b: [string, string, string]) =>
  team(name, [
    { race_number: a[0], vehicle: veh({ manufacturer: name, model: "X" }), drivers: [drv(a[1], a[1], a[2])] },
    { race_number: b[0], vehicle: veh({ manufacturer: name, model: "X" }), drivers: [drv(b[1], b[1], b[2])] },
  ]);

describe("Teams grid", () => {
  it("uses the identical TEAM 20 / ENTRY 40 / DRIVERS 40 structure for every team, whatever the driver names are", () => {
    const { container } = render(
      <>
        <TeamRow team={f1("Ferrari", ["16", "Charles", "Leclerc"], ["44", "Lewis", "Hamilton"])} />
        <TeamRow team={f1("McLaren", ["1", "Lando", "Norris"], ["81", "Oscar", "Piastri"])} />
        <TeamRow team={f1("Mercedes", ["12", "Kimi", "Antonelli-Longsurnamewithmanyletters"], ["63", "G", "R"])} />
      </>,
    );
    const rows = [...container.querySelectorAll("[data-testid=team-row]")];
    expect(rows).toHaveLength(3);
    for (const r of rows) {
      expect(r.className).toContain("lg:grid-cols-[1fr_2fr_2fr]");
      expect(r.querySelectorAll("[data-testid=entry-info]")).toHaveLength(1);
      expect(r.querySelectorAll("[data-testid=team-identity]")).toHaveLength(1);
      const grid = r.querySelector("[data-testid=driver-grid]")!;
      expect(grid.className).toContain("min-[480px]:grid-cols-2");
      expect(grid.querySelectorAll("[data-testid=driver-card]")).toHaveLength(2); // side by side, fixed 2-col grid
    }
  });

  it("groups Formula cars into one vehicle block and endurance cars into one block each", () => {
    const f1Entries = f1("Ferrari", ["16", "a", "A"], ["44", "b", "B"]).entries;
    expect(groupEntries(f1Entries)).toHaveLength(1);
    const crew = (n: string, names: string[]): Entry => ({ race_number: n, vehicle: veh({ model: "499P" }), drivers: names.map((x) => drv(x, x, x)) });
    const wec = [crew("50", ["a", "b", "c"]), crew("51", ["d", "e", "f"])];
    expect(groupEntries(wec)).toHaveLength(2);
    const { container } = render(<TeamRow team={team("Ferrari AF Corse", wec)} />);
    expect(container.querySelectorAll("[data-testid=entry-group]")).toHaveLength(2);
    expect(container.querySelectorAll("[data-testid=driver-card][data-drivers='3']")).toHaveLength(2);
    expect(container.querySelector("[data-testid=driver-grid]")).toBeNull();
  });

  it("supports a single-driver team without changing the column structure", () => {
    const { container } = render(<TeamRow team={team("Williams", [{ race_number: "23", vehicle: veh(), drivers: [drv("a", "Alex", "Albon")] }])} />);
    expect(container.querySelector("[data-testid=driver-grid]")!.className).toContain("min-[480px]:grid-cols-2");
  });
});
