import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import TeamRow from "@/components/TeamRow";
import type { Driver, Entry, Team } from "@/lib/types";

const drv = (first: string, last: string): Driver => ({ slug: `${first}-${last}`.toLowerCase(), first_name: first, last_name: last, nationality_code: "BE", image_url: null });
const gtwc = { slug: "gt-world-challenge-europe", name: "GT World Challenge Europe", short_name: "GTWC", category: "gt" as const, official_url: "", logo_url: null, active: true };
const f1 = { ...gtwc, slug: "formula-1", name: "Formula 1", short_name: "F1", category: "formula" as const };
const car = (n: string, make: string | null, model = "M4 GT3 EVO", cls: string | null = "Pro", crew = [drv("Charles", "Weerts"), drv("Kelvin", "van der Linde")]): Entry =>
  ({ race_number: n, vehicle: { manufacturer: make, model, class_name: cls, race_number: n, image_url: null, fallback_logo_url: null }, drivers: crew });
const mk = (slug: string, name: string, entries: Entry[], over: Partial<Team> = {}): Team =>
  ({ slug, name, short_name: null, logo_url: null, website_url: null, series: gtwc, vehicle: entries[0]?.vehicle ?? null, entries, ...over });

const mark = (c: HTMLElement) => c.querySelector("[data-testid=team-identity]")!.getAttribute("data-mark");
const logoSrc = (c: HTMLElement) => c.querySelector("[data-testid=team-mark] img")?.getAttribute("src");

describe("team identity priority", () => {
  it("shows the team logo from the registry (and API logo_url wins over it)", () => {
    const t = mk("mclaren", "McLaren", [car("81", "McLaren", "MCL40", null, [drv("Oscar", "Piastri")])], { series: f1 });
    const a = render(<TeamRow team={t} />);
    expect(mark(a.container)).toBe("team-logo");
    expect(logoSrc(a.container)).toBe("/assets/logos/teams/mclaren.png");
    a.unmount();
    const b = render(<TeamRow team={{ ...t, logo_url: "https://cdn.example/mclaren.svg" }} />);
    expect(logoSrc(b.container)).toBe("https://cdn.example/mclaren.svg");
  });

  it("falls back to the manufacturer logo when the team has no logo (spec example: Team WRT / BMW)", () => {
    const { container } = render(<TeamRow team={mk("team-wrt", "Team WRT", [car("32", "BMW"), car("46", "BMW")])} />);
    expect(mark(container)).toBe("manufacturer-logo");
    expect(logoSrc(container)).toMatch(/manufacturers\/bmw\./);
    expect(screen.getByText("Team WRT")).toBeInTheDocument();   // the name is always still there
  });

  it("does NOT borrow a manufacturer logo for a team that runs several makes", () => {
    const { container } = render(<TeamRow team={mk("mixed-team", "Mixed Team", [car("1", "BMW"), car("2", "Porsche")])} />);
    expect(mark(container)).toBe("wordmark");
  });

  it("falls back to the typeset team name when neither logo exists (missing registry entry)", () => {
    const { container } = render(<TeamRow team={mk("not-in-registry", "Unknown Racing", [car("9", "Corvette")])} />);
    expect(mark(container)).toBe("wordmark");
    expect(container.querySelector("[data-testid=team-mark]")).toBeNull();
    expect(screen.getByTestId("team-name")).toHaveTextContent("Unknown Racing");
    expect(container.querySelectorAll("img")).toHaveLength(0);
  });

  it("uses the neutral GRIDLINE placeholder when there is not even a name", () => {
    const { container } = render(<TeamRow team={mk("x", "  ", [car("9", null)])} />);
    expect(mark(container)).toBe("placeholder");
    expect(screen.getByLabelText("GRIDLINE placeholder")).toBeInTheDocument();
  });

  it("a broken asset never blocks the UI: team logo → manufacturer logo → wordmark", () => {
    const { container } = render(<TeamRow team={mk("mclaren", "McLaren", [car("81", "BMW")], { series: f1 })} />);
    expect(mark(container)).toBe("team-logo");
    fireEvent.error(container.querySelector("[data-testid=team-mark] img")!);
    expect(mark(container)).toBe("manufacturer-logo");
    fireEvent.error(container.querySelector("[data-testid=team-mark] img")!);
    expect(mark(container)).toBe("wordmark");
    expect(screen.getByTestId("team-name")).toHaveTextContent("McLaren");
  });

  it("logos are contain-fit in one fixed box (never stretched)", () => {
    const { container } = render(<TeamRow team={mk("af-corse", "AF Corse", [car("81", "Ferrari")])} />);
    expect(container.querySelector("[data-testid=team-mark]")!.className).toMatch(/\bh-14\b.*\bw-44\b/);
    const m = render(<TeamRow team={mk("kessel-racing", "Kessel Racing", [car("9", "BMW")])} />);
    const sec = m.container.querySelector("[data-testid=team-mark]")!;  // manufacturer fallback: smaller and dimmer, never the primary mark
    expect(sec.getAttribute("data-secondary")).toBe("true");
    expect(sec.className).toMatch(/\bh-8\b/);
    expect(container.querySelector("[data-testid=team-mark] img")!.className).toContain("object-contain");
  });
});

describe("EventEntry content", () => {
  it("shows team logo, race number, manufacturer + model, class and drivers in TEAM / ENTRY / DRIVERS columns", () => {
    const { container } = render(<TeamRow team={mk("team-wrt", "Team WRT", [car("32", "BMW")])} />);
    expect(container.querySelector("article")!.className).toContain("lg:grid-cols-[1fr_2fr_2fr]");
    expect(logoSrc(container)).toBeTruthy();
    const entry = within(screen.getByTestId("entry-info"));
    expect(entry.getByTestId("race-number")).toHaveTextContent("#32");
    expect(entry.getByTestId("entry-car")).toHaveTextContent("BMW M4 GT3 EVO");
    expect(entry.getByTestId("entry-class")).toHaveTextContent("Pro");
    expect(within(screen.getByTestId("driver-card")).getByText("Weerts")).toBeInTheDocument();
    expect(within(screen.getByTestId("driver-card")).getByText("van der Linde")).toBeInTheDocument();
  });

  it("the secondary manufacturer logo is small, optional, and survives a broken file", () => {
    const { container } = render(<TeamRow team={mk("team-wrt", "Team WRT", [car("32", "BMW"), car("46", "Corvette")])} />);
    const groups = [...container.querySelectorAll("[data-testid=entry-group]")];
    expect(groups[0].querySelector("[data-testid=manufacturer-logo]")!.className).toContain("w-16");
    expect(groups[1].querySelector("[data-testid=manufacturer-logo]")).toBeNull();   // Corvette: no asset → text only
    expect(groups[1]).toHaveTextContent("Corvette M4 GT3 EVO");
    fireEvent.error(groups[0].querySelector("[data-testid=manufacturer-logo] img")!);
    expect(groups[0].querySelector("[data-testid=manufacturer-logo]")).toBeNull();
    expect(groups[0]).toHaveTextContent("BMW M4 GT3 EVO");
  });

  it("entries without number, class or manufacturer render without empty chrome", () => {
    const { container } = render(<TeamRow team={mk("t", "T", [{ race_number: null, vehicle: null, drivers: [drv("A", "B"), drv("C", "D")] }])} />);
    expect(container.querySelector("[data-testid=race-number]")).toBeNull();
    expect(container.querySelector("[data-testid=entry-class]")).toBeNull();
    expect(screen.getByText("B")).toBeInTheDocument();
  });
});

describe("scale and long names", () => {
  it("renders 60 teams with the identical grid and complete identity each", () => {
    const slugs = ["af-corse", "rowe-racing", "team-wrt", "kessel-racing", "garage-59"];
    const teams = Array.from({ length: 60 }, (_, i) => mk(i < 5 ? slugs[i] : `team-${i}`, `Team ${i}`, [car(String(i), i % 3 ? "BMW" : "Corvette")]));
    const { container } = render(<>{teams.map((t) => <TeamRow key={t.slug} team={t} />)}</>);
    const rows = container.querySelectorAll("[data-testid=team-row]");
    expect(rows).toHaveLength(60);
    for (const r of rows) {
      expect(r.className).toContain("lg:grid-cols-[1fr_2fr_2fr]");
      expect(r.querySelectorAll("[data-testid=team-identity]")).toHaveLength(1);
      expect(r.querySelectorAll("[data-testid=team-name]")).toHaveLength(1);
      expect(["team-logo", "manufacturer-logo", "wordmark"]).toContain(r.querySelector("[data-testid=team-identity]")!.getAttribute("data-mark"));
    }
    const marks = [...container.querySelectorAll("[data-testid=team-identity]")].map((e) => e.getAttribute("data-mark"));
    expect(new Set(marks)).toEqual(new Set(["team-logo", "manufacturer-logo", "wordmark"]));
  });

  it("long team names wrap inside the TEAM column instead of breaking the grid", () => {
    const long = "Mercedes - AMG Team Verstappen Racing powered by Extraordinarily-Long-Sponsor-Name Motorsport GmbH & Co. KG";
    const { container } = render(<TeamRow team={mk("long-one", long, [car("3", "Mercedes-AMG")])} />);
    const name = screen.getByTestId("team-name");
    expect(name).toHaveTextContent(long);
    expect(name.className).toContain("break-words");
    expect(container.querySelector("[data-testid=team-identity]")!.className).toContain("min-w-0");
    expect(container.querySelector("article")!.className).toContain("lg:grid-cols-[1fr_2fr_2fr]");
  });
});
